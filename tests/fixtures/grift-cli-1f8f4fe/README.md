# grift-cli producer fixtures

`aggregate.json` と `named-public.json` は `grift-cli-dev` の commit
`1f8f4fe` にある `build_contribution_bundle()` から、固定の合成
`report-v2` を入力して生成した公開 payload です。

この fixture は受信側の正例を固定するためのものです。CLI 側 CI はこの
リポジトリの validator を exact commit で取得し、同じ producer を実行して
送信側と受信側の drift を別途検出します。`masked` / `raw` は公開 intake の
正例になり得ないため、mutation test で hard reject を確認します。
