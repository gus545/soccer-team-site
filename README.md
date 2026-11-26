# ors-soccer

Schedule, results, standings, shirt-colour pick and a subscribable calendar for **The 7 Deadly Shins**
(Ottawa Rec Sports, Sunday co-ed soccer, East), published at **https://soccer.macgillivary.dev**.

ORS runs its leagues on TeamLinkt. The scraper calls the same public JSON endpoints the league
site uses (`getAllEvents`, `getStandings`) and renders a static site. It needs only the Python 3.11+
standard library.

```
python -m ors.build dist     # writes dist/index.html, data.json, shins.ics, styles.css
python -m pytest -q
```

## How it finds the team

`config.json` holds the team name and season prefix (`Sun-Soccer`). Each run, the scraper:

1. Reads the season list from the league site and keeps the `Sun-Soccer-*` seasons, newest first.
2. Picks the newest seasons whose standings include the team (`seasons_to_show`, default 2), so
   the page rolls over to Spring automatically once the team is registered.
3. Finds the team's division by checking each division's standings, then pulls the team's games.

## Shirt colours

TeamLinkt doesn't publish team colours, so set them in `colours.json`. Fill in our team, plus
opponents if you know theirs. The rule is the same as in the Discord bot: home wears primary, and
away switches to secondary (then `alt`) on a clash.

## Attendance

The next-game card has **In / Maybe / Out** buttons. The first tap asks for your name, the
browser remembers it, and tapping your current answer again clears it. There's no login, to keep
it as easy as an Instagram poll. Share `https://soccer.macgillivary.dev/#rsvp` in the group chat.

`api/attendance.py` is a Lambda function served through CloudFront at `/api/attendance`, storing
answers in DynamoDB (they expire after 120 days). It only accepts games listed in the published
`data.json`, keeps names short and plain, and allows at most 40 entries per game.

## Team wallet

The page shows a **Team wallet** card: balance, money in/out, the latest transactions and who
has paid dues. It's a ledger you edit by hand in `wallet.json` and push, just like `colours.json`.
There's deliberately no way to change it from the site, since anyone can open the page.

```json
{
  "currency": "CAD",
  "how_to_pay": "e-Transfer the captain",
  "dues": { "label": "Winter 2026-27 dues", "amount": 100, "since": "2026-11-01",
            "players": ["Angus", "Bea"] },
  "entries": [
    { "date": "2026-11-02", "note": "Winter dues", "amount": 100, "who": "Angus" },
    { "date": "2026-11-05", "note": "League fee", "amount": -1200 }
  ]
}
```

- Positive amounts are money in, negative are money out. The balance is the sum of all entries.
- A payment with `who` set counts toward that player's dues if it's dated on or after
  `dues.since` (names match case-insensitively). Dues are hidden while `amount` is 0 or
  `players` is empty.
- A malformed entry (bad date, non-numeric amount, fractions of a cent, missing note) fails the
  build, so a typo never shows a wrong balance.
- Everything in `wallet.json` is public on the site and in `data.json`.

## Deploy

Infra and the attendance API (us-east-1, because CloudFront certificates must live there).
Re-run this after changing `infra/` or `api/`:

```
aws login --remote        # on WSL; plain `aws login` works where the browser callback does
ZONE=$(aws route53 list-hosted-zones-by-name --dns-name macgillivary.dev \
        --query 'HostedZones[0].Id' --output text | cut -d/ -f3)
sam deploy --template-file infra/template.yml --stack-name ors-soccer --region us-east-1 \
  --resolve-s3 --s3-prefix ors-soccer \
  --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
  --parameter-overrides HostedZoneId=$ZONE GitHubRepo=gus545/soccer-team-site
aws cloudformation describe-stacks --region us-east-1 --stack-name ors-soccer \
  --query 'Stacks[0].Outputs' --output table
```

Then set the repository variables `S3_BUCKET` and `DEPLOY_ROLE_ARN` from those outputs
(Settings → Secrets and variables → Actions → Variables). The workflow scrapes every 3 hours,
every 30 minutes on Sunday afternoons and evenings, and on every push to `main`.

> GitHub pauses scheduled workflows on public repos after 60 days without a commit. If the page
> goes stale in the off-season, push any commit or re-enable the workflow in the Actions tab.
