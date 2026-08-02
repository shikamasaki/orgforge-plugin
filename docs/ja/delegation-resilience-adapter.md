# Delegation Resilience v0alpha2 export adapter

`tools/delegation_resilience_export.py export` は一方向のexport-only adapterです。OrgForgeの証拠を
固定したDR v0alpha2のpacketへ写像します。入力の台帳・constitution・exerciseは変更しません。

## Assurance Graphの状態（fail-closed stub）

固定したDR v0alpha2 commitには、機械可読なAssurance Graph schema、edge semantics、graph verifier
contractがまだありません。そのためOrgForgeは独自のグラフ意味論を作りません。`graph` commandは
consumer-held lockに `assuranceGraph.schemaRef` と `assuranceGraph.verifierCodeDigest` が宣言される
まで失敗し、partial artifactを出力しません。

将来の写像では、actor、intent/capability、attempt/exercise、evidence、attestation/artifact、明示された
dependencyだけをsourceRefとartifact digest付きで出力します。edge、stable ID、recovery claimの判定は
DR schemaとverifierの責務です。欠測、推測、duplicate、dangling reference、digest mismatchはすべて
fail-closedとし、packet/graphの成功はrecovery capabilityの実証を意味しません。

この境界の目的は、グラフの存在を新しい保証と扱うことではなく、証拠・依存・外部効果・復旧可能性を
改変耐性と再現性を持って説明できるようにすることです。
