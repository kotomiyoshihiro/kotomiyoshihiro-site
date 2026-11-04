# kotomiyoshihiro-site
Official site for Kotomi Yoshihiro

## 動画の一覧(videos/)

`videos/index.html` は `videos/videos.json` を読み、公開の日時(日本時間)を過ぎた YouTube ショートだけを単元ごとに出す。
`videos.json` は手で直さない。YouTube の予約を足したら `python tools/build_videos.py` を流し(既定で `../personal-hub/publicity/kotomi-yoshihiro/posting-schedule.md` ほかを読む。`--src` で場所を変えられる)、できた `videos/videos.json` を commit する。

## 解析

- Google Search Console: URL プレフィックスのプロパティ `https://kotomiyoshihiro.com/`(2026-11-04 登録、所有者は yas614@gmail.com)。所有確認は `index.html` の `<meta name="google-site-verification">`。**このタグを消すと確認が外れるので消さない。**
- Cloudflare Web Analytics: 未設定(2026-11-04、Cloudflare にログインした Chrome がなかった)。
