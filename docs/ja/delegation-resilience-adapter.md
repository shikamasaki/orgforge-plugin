# Delegation Resilience v0alpha2 export adapter

`tools/delegation_resilience_export.py export` は一方向のexport-only adapterです。OrgForgeの証拠を
固定したDR v0alpha2のpacketへ写像します。入力の台帳・constitution・exerciseは変更しません。

## Assurance Graph export

transactional-action v0alpha2とは別に、DR Assurance Graph v0alpha1のtag object・commit・schema digest・
verifier digestをconsumer-held lockで固定しています。`graph` commandは固定archiveだけをimportし、schemaと
verifierのdigestを突合して、standalone verifierが成功した場合だけartifactを出力します。不一致や失敗時は
partial artifactを出力しません。

現在は明示されたreviewer-outageのexercise、report由来のevidence/artifact、およびschemaで定義された
`produces_artifact`だけをsourceRefとartifact digest付きで出力します。actor、claim、capability、dependency、
external effectや推測edgeは生成しません。edge semanticsとrecovery claim判定はDRの責務です。欠測、推測、
duplicate、dangling reference、digest mismatchはfail-closedとし、`GRAPH_VERIFIED`はrecovery capabilityや
human takeoverの実証を意味しません。

この境界の目的は、グラフの存在を新しい保証と扱うことではなく、証拠・依存・外部効果・復旧可能性を
改変耐性と再現性を持って説明できるようにすることです。
