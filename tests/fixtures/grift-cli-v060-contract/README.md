# grift-cli producer fixtures

`aggregate.json` と `named-public.json` は v0.6 の版契約に対する固定の
合成 `report-v2` 正例です。特定commitの実行証跡ではありません。

この fixture は受信側の正例を固定するためのものです。CLI 側 CI はこの
リポジトリの validator を exact commit で取得し、実producerを実行して
送信側と受信側の drift を別途検出します。`masked` / `raw` は公開 intake の
正例になり得ないため、mutation test で hard reject を確認します。
