# B-Side: Music RSS

A GitHub Pages site that pulls every music feed in the directory into one reader and republishes them as combined RSS feeds. A GitHub Action fetches all ~1,250 source feeds every three hours.

**What's here**
- `sources.json`: 1,618 sources (1,249 with native RSS/Atom, YouTube or podcast feeds, plus 369 Instagram handles)
- `scripts/build.py`: fetches every feed and writes the site
- `site/`: the published page, `feeds/*.xml` combined feeds, `music-feeds.opml`, `directory.csv` (all 2,545 directory entries)

**Combined feeds** (under `https://<user>.github.io/<repo>/feeds/`): `all.xml`, `publications.xml`, `blogs.xml`, `hiphop.xml`, `electronic.xml`, `rock.xml`, `indie.xml`, `pop.xml`, `jazz.xml`, `roots.xml`, `global.xml`, `industry.xml`, `newsletters.xml`, `podcasts.xml`, `youtube.xml`, `instagram.xml`.

**Setup (once)**
1. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
2. Actions tab → "Update feeds and publish" → **Run workflow**.

**Instagram (optional).** Instagram has no RSS. To include the Instagram accounts, run an [RSSHub](https://docs.rsshub.app/) instance with an Instagram login cookie and add a repository variable `RSSHUB_BASE` (Settings → Secrets and variables → Actions → Variables), e.g. `https://rsshub.example.com`.

**Edit sources.** Add or remove entries in `sources.json` (`feed` is the RSS URL, `genre` decides the section). Pushing the change triggers a rebuild.
