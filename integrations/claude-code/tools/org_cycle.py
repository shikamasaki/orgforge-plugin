#!/usr/bin/env python3
"""org_cycle — 1サイクル分の配管を1コマンドで回す（docs/11 §0d）。

**なぜこれが要るのか。** `/org-work` は「こういうイベントを打て」という散文の指示で、実行するのは
エージェントだった。実地で1サイクル（Issue 2件）あたり **11コマンド**を手で叩いており、18 Issue
なら約90回になる。そのうち1回でも間違えれば台帳の整合が崩れる。

さらに悪いのは `parent` の扱いだった。フェーズ連鎖は親 objective の admit を継承する（docs/11 §2）
のに、その `parent` の値を**人が Issue から目で拾って手打ち**していた。継承の実装を入れても、
値が手打ちである限り取り違えが起きる — **拾えるものを拾わせないのは設計の怠慢**である。

このツールは「順序と actor が決まっている配管」だけを引き受ける。**判断は引き受けない** —
何を選ぶか、誰に委ねるか、admit するかは役割の仕事であり、ここでは自動化しない（docs/03 §6.5 の
「forced delegation は設計エラー、forced invariant は正しい」の線引きをそのまま踏襲する）。

  org_cycle.py begin    --role R --issue N [--phase implement] [--agent A]
      claim → spec_delegated → phase_started（parent 自動解決）→ cycle_started → Issue へ log
  org_cycle.py complete --role R --issue N --outputs TEXT
                        (--domain-model-updated REF | --domain-model-none WHY)
      cycle_completed（domain_model 必須）→ Issue へ log → stage done
  org_cycle.py plan     --role R --issue N [...]
      **何も実行せず**、打つイベント列を印字する（--dry-run 相当）

Exit: 0 ok / 3 台帳が拒否（順序違反など）/ 8 judge preflight 失敗 /
      9 installed-organ binding 不備 / 10 contended / 2 usage・設定エラー
"""
import argparse
import json
import os
import re
import subprocess
import sys


import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from orgcycle._core import banner
from orgcycle.cycle import cmd_begin, cmd_complete, cmd_plan
from orgcycle.judge import cmd_verify, cmd_record, cmd_rework, cmd_intake
from orgcycle.ship import cmd_handback, cmd_integrate
from orgcycle.inspect import cmd_show, cmd_gc, cmd_touched


def main(argv):
    p = argparse.ArgumentParser(prog="org_cycle", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("begin", "plan"):
        q = sub.add_parser(name)
        q.add_argument("--role", required=True, help="委譲する側（supervisor / 部門長）")
        q.add_argument("--issue", required=True, type=int, help="task Issue 番号")
        q.add_argument("--agent", help="実際に作る側（省略時は --role と同じ）")
        q.add_argument("--phase", default="implement", help="開始するフェーズ（既定 implement）")
        q.add_argument("--parent", help="親 objective 番号（省略時は Issue から自動解決）")
        q.add_argument("--candidate-id", dest="candidate_id",
                       help="省略時は Issue の candidate_id トレーラから読む")
        q.add_argument("--base", help="worktree を切る元（既定 develop）")
        q.add_argument("--why", help="なぜ今これを選んだか（attention_allocated の reason）")
        q.add_argument("--no-check", dest="no_check", action="store_true",
                       help="着手前の確認（依存の状態・人間の作業待ち）を出さない")
        q.add_argument("--no-worktree", dest="no_worktree", action="store_true",
                       help="worktree を作らない。**並列で回すなら使わないこと** — 同一ツリーで"
                            "並列 maker を走らせると、あるIssueのコミットが別Issueのブランチに"
                            "載る事故が起きる（実際に起きた）。単発の逐次作業のときだけ。")
    q = sub.add_parser("verify", help="gate/skeptic を起動する材料を組み立てる（判定はしない）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", required=True, choices=("gate", "skeptic"))
    # phase は review_subject の一部（どのフェーズの判定か）。
    q.add_argument("--phase", default=None,
                   help="判定するフェーズ（review_subject_id に入る）")
    q.add_argument("--base", dest="base", default=None,
                   help="統合先 ref（省略時は origin/develop/develop/origin/main/main の順で解決）")
    q.add_argument("--subject-root", dest="subject_root", default=None,
                   help="判定対象の checkout を明示する（既定は Issue の worktree "
                        ".orgforge/wt/issue-<N>）。worktree 運用でないレイアウトを意図して"
                        "判定するときだけ使う — cwd への暗黙 fallback はしない（#101）")
    # 記録のためだけに judge を起動させない。cross-harness の org では verify が実際に
    # headless judge を回すので、subject を知るのに数分待つのは筋が悪い（実測）。
    q.add_argument("--print-subject", action="store_true",
                   help="review_subject_id だけを出して終わる（judge は起動しない）")

    q = sub.add_parser("touched", help="本番資産への変更を台帳に残す（DDL・権限・インフラ）")
    q.add_argument("--target", required=True, help='何に対してか（例 supabase:<project>）')
    q.add_argument("--op", required=True, help="apply_migration / revoke / grant / deploy …")
    q.add_argument("--name", help="対象の名前（マイグレーション名・関数名など）")
    q.add_argument("--by", required=True, help="誰が入れたか")
    q.add_argument("--authority", required=True,
                   help="誰の権限で入れたか（issue-N の一部 / CEO の明示指示 / 自己判断）")
    q.add_argument("--issue", type=int, help="関連する Issue")
    q.add_argument("--reversible", action="store_true", help="戻せるなら付ける")
    q.add_argument("--rollback", help="戻し方（reversible なら書くこと）")

    q = sub.add_parser("show", help="1つの Issue の全体像（判定履歴・いま何待ちか）")
    q.add_argument("--issue", required=True, type=int)

    q = sub.add_parser("gc", help="溜まった worktree を片付ける（未コミットのものは残す）")
    q.add_argument("--base", default="develop")
    q.add_argument("--all", action="store_true", help="未統合のものも対象にする")

    q = sub.add_parser("intake", help="subagent の報告が成果物の形になっているかを検査する")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", required=True, help="gate / skeptic / maker")
    q.add_argument("--report", required=True,
                   help="subagent が返した報告（`-` で標準入力から読む）")

    q = sub.add_parser("rework", help="reject/refuted を受けて rework を発注したことを記録する")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--after", required=True, choices=("reject", "refuted"),
                   help="どちらの判定を受けての rework か")
    q.add_argument("--by", required=True, help="発注した役割（監督）")
    q.add_argument("--reason", required=True, help="maker に直させることを1行で")
    q.add_argument("--round", default="1", help="何周目か（冪等キーに入る）")
    q.add_argument("--to", help="誰に発注したか")

    q = sub.add_parser("record", help="済んだ判定を遡って台帳に記録する（backfill 印が付く）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--event", required=True, help="integration_admitted / refutation_attempted など")
    q.add_argument("--verdict", required=True)
    q.add_argument("--by", required=True, help="誰の判定か")
    q.add_argument("--why", required=True, help="何を見て、何が決め手になったか")
    q.add_argument("--command", help="当時実行したコマンド")
    q.add_argument("--result", help="その実出力")
    q.add_argument("--base", default="develop")

    q = sub.add_parser("handback", help="feature ブランチを push → develop 宛 PR → Issue に紐付け")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--branch", help="省略時は Issue から決定的に導出")
    q.add_argument("--base", default="develop")
    q.add_argument("--summary", help="何を作ったか（1行）")
    q.add_argument("--result", help="DoD コマンドの実出力（PR body と log に入る）")
    q.add_argument("--files", help="変更ファイル")

    q = sub.add_parser("integrate", help="develop への fan-in（前提照合 → マージ → 統合後テスト → 記録）")
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--role", default="integrator", help="統合を回す役割（記録の actor）")
    q.add_argument("--branch", help="省略時は Issue から決定的に導出")
    q.add_argument("--base", default="develop")
    q.add_argument("--test", default="npm test", help="統合後に走らせる全体テスト")
    q.add_argument("--force", action="store_true",
                   help="gate/skeptic の前提が無くても進める。**理由を記録すること**")
    q.add_argument("--plan", action="store_true",
                   help="何も実行せず、何を統合するか・衝突しそうな箇所を見せる")

    q = sub.add_parser("complete")
    q.add_argument("--role", required=True)
    q.add_argument("--issue", required=True, type=int)
    q.add_argument("--agent")
    q.add_argument("--outputs", required=True, help="何を作ったか（1行）")
    q.add_argument("--command", required=True,
                   help="DoD コマンド（verbatim。他人が再実行できる形で）")
    q.add_argument("--result", required=True,
                   help="そのコマンドの**実出力**（失敗込み。「通った」は不可 — log が拒否する）")
    q.add_argument("--files", help="変更したファイル")
    q.add_argument("--new-surface", dest="new_surface", action="append",
                   help="このサイクルで外に晒した面（誰が呼べるか / 何ができるか）。複数可")
    q.add_argument("--new-surface-none", dest="new_surface_none",
                   help="公開面を増やしていない理由（明示的な否定）")
    q.add_argument("--learned",
                   help="次のサイクルにも効く学び（doctrine に propose する。admit は gate）")
    q.add_argument("--affects", help="その学びが効く役割（カンマ区切り）")
    q.add_argument("--confidence", type=float, default=0.7,
                   help="その学びへの確信度 0..1（既定 0.7）")
    q.add_argument("--review-days", dest="review_days", type=int, default=180,
                   help="その学びを再確認するまでの日数（既定 180）")
    q.add_argument("--domain-model-updated", dest="domain_model_updated",
                   help="このサイクルが確立したドメイン規則への参照")
    q.add_argument("--domain-model-none", dest="domain_model_none",
                   help="何も確立しなかった理由（明示的な否定。docs/11 §4d）")
    q.add_argument("--candidate-id", dest="candidate_id")
    a = p.parse_args(argv[1:])
    banner()
    return {"begin": cmd_begin, "complete": cmd_complete, "plan": cmd_plan,
            "verify": cmd_verify, "integrate": cmd_integrate, "handback": cmd_handback, "gc": cmd_gc, "record": cmd_record, "rework": cmd_rework, "intake": cmd_intake, "show": cmd_show, "touched": cmd_touched}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
