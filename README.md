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

## Deploy

One-time infra (us-east-1, because CloudFront certificates must live there):

```
aws login
ZONE=$(aws route53 list-hosted-zones-by-name --dns-name macgillivary.dev \
        --query 'HostedZones[0].Id' --output text | cut -d/ -f3)
aws cloudformation deploy --region us-east-1 --stack-name ors-soccer \
  --template-file infra/template.yml --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides HostedZoneId=$ZONE GitHubRepo=gus545/soccer-team-site
aws cloudformation describe-stacks --region us-east-1 --stack-name ors-soccer \
  --query 'Stacks[0].Outputs' --output table
```

Then set the repository variables `S3_BUCKET` and `DEPLOY_ROLE_ARN` from those outputs
(Settings → Secrets and variables → Actions → Variables). The workflow scrapes every 3 hours,
every 30 minutes on Sunday afternoons and evenings, and on every push to `main`.

> GitHub pauses scheduled workflows on public repos after 60 days without a commit. If the page
> goes stale in the off-season, push any commit or re-enable the workflow in the Actions tab.
