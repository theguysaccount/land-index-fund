"""Settings. Everything a deploy might change comes from the environment, so the base URL is one setting."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SITE_SRC = os.path.join(ROOT, "site")

SITE_NAME = "US County Land Index"
SITE_SHORT = "County Land Index"
TAGLINE = "Land prices per acre for every US county, from official USDA and FHFA data"

REPO = os.environ.get("LI_REPO", "theguysaccount/land-index-fund")
REPO_URL = "https://github.com/" + REPO
# The public address of the site, without a trailing slash: one setting. Fleet convention (~/code/DOMAIN_ROLLOUT.md):
# repository variable SITE_URL; LI_BASE_URL also works.
BASE_URL = (os.environ.get("SITE_URL") or os.environ.get("LI_BASE_URL")
            or "https://theguysaccount.github.io/land-index-fund").rstrip("/")

# Optional keys (see OPERATIONS.md). Empty means the feature stays off.
SUPPORT_URL = os.environ.get("LI_SUPPORT_URL", "").strip()
GOATCOUNTER = os.environ.get("LI_GOATCOUNTER", "").strip()
GOOGLE_VERIFY = os.environ.get("LI_GOOGLE_VERIFY", "").strip()

# Identifies this project to the data publishers. The repository is the contact address.
USER_AGENT = "land-index-fund/1.0 (+%s)" % REPO_URL


def base_path():
    """Path part of BASE_URL: '/land-index-fund' on GitHub Pages, '' on a custom domain."""
    rest = BASE_URL.split("://", 1)[-1]
    return ("/" + rest.split("/", 1)[1]).rstrip("/") if "/" in rest else ""
