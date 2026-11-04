# kotomiyoshihiro-site
Official site for Kotomi Yoshihiro

## 動画の一覧(videos/)

`videos/index.html` は `videos/videos.json` を読み、公開の日時(日本時間)を過ぎた YouTube ショートだけを単元ごとに出す。
`videos.json` は手で直さない。YouTube の予約を足したら `python tools/build_videos.py` を流し(既定で `../personal-hub/publicity/kotomi-yoshihiro/posting-schedule.md` ほかを読む。`--src` で場所を変えられる)、できた `videos/videos.json` を commit する。
