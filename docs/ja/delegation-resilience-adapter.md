# Delegation Resilience v0alpha2 export adapter

`tools/delegation_resilience_export.py export` は一方向のexport-only adapterです。OrgForgeの証拠を
固定したDR v0alpha2のpacketへ写像します。入力の台帳・constitution・exerciseは変更しません。

## Assurance Graph export

`tools/assurance_graph_export.py export` は第2の一方向adapterで、v0alpha2 packet adapterとは
別ファイル・別lockです。v0alpha2側のtool・lock・CLIには一切手を入れません。同じ3つのOrgForge入力に
加えて、明示の `--observed-at` UTC timestamp（report protocolは時刻を持たないため）を受け取り、
graph packet（`graph.json`、固定DR verifierの `verification-result.json`、source artifacts、
固定Graph verifierのstandaloneコピー）を出力します。

lockは `integrations/delegation-resilience/assurance-graph-v0alpha1.lock.json` です。
`assurance-graph-v0alpha1.1` のtag object・commit・schema digest・standalone Graph verifier code
digestを固定します（DR自身のrelease lockが同一commitで公開する値と同一）。exportはtag参照をDR
checkoutに対して照合し、固定commitのpath-safeな `git archive` からのみGraph verifierを新規
subprocessで実行します。schemaとverifier codeのdigestはarchiveから再計算してlockと突合し、
不一致なら何も出力しません。repo-localな `git replace` refで内容を差し替えられないよう、
git呼び出しは `--no-replace-objects` で行います。

写像の規則:

- source artifactから直接読めるnode/edge（exercise、report evidence、constitution artifact、
  reviewer/harness dependency、宣言されたshared-fateとdepends_on）は `observed`。
- adapterは意味論的な `supports` edgeを推測しません。`NOT_DEMONSTRATED` のclaim nodeを
  保持することはありますが、reportやconstitutionをsupport evidenceへ変換しません。
  supportの意味はDR verifierだけが所有し、recovery capabilityが要求・返却された場合は
  exporterがfail-closedします。

duplicate、dangling reference、digest mismatchは固定DR verifierがfail-closedで拒否します。
`GRAPH_VERIFIED` はグラフ構造・source artifact digest・参照・再現性の証明にすぎません。
recovery capability、human takeover、deployment approval、authorizationの実証ではなく、
これらはfacilitated human drillと実地のrecovery exerciseが存在するまで `NOT_DEMONSTRATED` の
ままです。
