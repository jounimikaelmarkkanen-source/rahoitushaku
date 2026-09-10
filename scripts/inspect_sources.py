"""Read public funding endpoints and store responses for adapter development."""
import argparse
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request

URLS = {
    "eu-faq-detail": "https://api.tech.ec.europa.eu/search-api/prod/rest/document/12125?apiKey=SEDIA_FAQ",
    "eu-missing-detail": "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/HORIZON-CL4-2024-HUMAN-01-34.json",
    "eu-missing-energy": "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/EE-07-2014.json",
    "hae-calls-ui": "https://www.haeavustuksia.fi/static/js/732.06f8230a.chunk.js",
    "hae-form-preview": "https://www.haeavustuksia.fi/api/haku/va-tem-2026-16/hakemuslomake/HakijanTiedot",
    "eu-faq-year": "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA_FAQ&text=***&pageSize=2&pageNumber=1",
    "eu-faq-list": "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA_FAQ&text=***&pageSize=100&pageNumber=1",
    "eu-opportunities-main": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/assets/elements/sedia-opportunities-eui19-remote-el-ui/bundles/main.js",
    "eu-opportunities": 'https://ec.europa.eu/info/funding-tenders/opportunities/portal/assets/elements/sedia-opportunities-eui19-remote-el-ui/bundles/entry-2.0.2.js',
    "eu-module": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/assets/elements/sedia-opportunities-eui19-remote-el-ui/package.json",
    "eu-loader": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/chunk-IFUCHIQQ.js",
    "eu-config": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/assets/openid-login-config.json",
    "eu-detail-current": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/data/topicDetails/BG-04-2017.json",
    "eu-main": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/main-U33VY6UU.js",
    "eu-chunk-base": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/chunk-KNYOQIIN.js",
    "eu-chunk-shared": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/chunk-TWZW5B45.js",
    "eu-portal": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/horizon-eic-2026-accelerator-01",
    "hae-criteria": "https://www.haeavustuksia.fi/api/haku/va-lou-2026-5/hakuilmoitus/arviointiperusteet",
    "hae-eligibility": "https://www.haeavustuksia.fi/api/haku/va-lou-2026-5/hakuilmoitus/myontoperusteet",
    "hae-additional": "https://www.haeavustuksia.fi/api/haku/va-lou-2026-5/hakuilmoitus/lisaehdot",
    "eu-detail-legacy": "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/BG-04-2017.json",
    "nordic-culture-programmes": "https://www.nkk.org/en/apply-for-funding/",
    "skr-hakija": "https://skr.fi/apurahat/apurahan-hakijalle/",
    "nessling": "https://nessling.fi/",
    "sitra-calls": "https://www.sitra.fi/wp-json/wp/v2/funding_request?per_page=100&page=1&lang=fi",
    "sitra-store": "https://www.sitra.fi/wp-content/themes/sitra-25/build/js/blocks/archive-content/store.js",
    "sitra-view": "https://www.sitra.fi/wp-content/themes/sitra-25/build/js/blocks/archive-content/view.js",
    "sitra-page": "https://www.sitra.fi/wp-json/wp/v2/pages/168269",
    "maaseutu": "https://www.ruokavirasto.fi/tuet/maaseudun-palvelut-ja-elinkeinojen-kehittaminen/",
    "ceb": "https://coebank.org/en/project-financing/sectors/",
    "hae-env": "https://www.haeavustuksia.fi/env.js",
    "hae-main": "https://www.haeavustuksia.fi/static/js/main.6cabdea7.js",
    "eura": "https://eura2021.fi/hakuilmoitukset/",
    "rr": "https://rakennerahastot.fi/rahoitushaut",
    "pirkanmaa": "https://www.pirkanmaa.fi/rahoitus/",
    "eu-doc": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis",
    "hae-list": "https://www.haeavustuksia.fi/api/haku/list-items?Pagination.Page=1&Pagination.PageSize=100&Language=fi&ShowFuture=true&ShowOngoing=true&ShowEnded=false&HideExternal=false",
    "eura-detail": "https://eura2021.fi/hakuilmoitukset/hakuilmoitus/85e7f2c6-b780-40b5-8c71-db2c8ff7f866/",
    "eu-api": "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***&pageSize=2&pageNumber=1",
    "hae-detail": "https://www.haeavustuksia.fi/api/haku/va-lou-2026-5/hakuilmoitus/perustiedot",
    "hae-general": "https://www.haeavustuksia.fi/api/haku/va-lou-2026-5/hakuilmoitus/yleistiedot",
    "eu-year": "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***&pageSize=2&pageNumber=1",
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    out = pathlib.Path("tmp/research")
    out.mkdir(parents=True, exist_ok=True)
    for name in args.names or URLS:
        url = URLS[name]
        try:
            data = None
            headers = {"User-Agent": "FundingRegistryResearch/0.1"}
            if name in ("eu-api", "eu-year", "eu-faq-list", "eu-faq-year"):
                query = {"bool": {"must": [{"terms": {"type": ["1"]}}, {"terms": {"status": ["31094501", "31094502"]}}, {"term": {"language": "en"}}]}}
                if name in ("eu-faq-list", "eu-faq-year"):
                    query = {"bool": {"must": [{"term": {"language": "en"}}]}}
                if name == "eu-faq-year":
                    query["bool"]["must"].append({"range": {"publicationDate": {"gte": "1735689600000", "lt": "1767225600000"}}})
                if name == "eu-year":
                    query["bool"]["must"][1] = {"terms": {"status": ["31094501", "31094502", "31094503"]}}
                    query["bool"]["must"].append({"range": {"startDate": {"gte": "2026-01-01T00:00:00Z", "lt": "2027-01-01T00:00:00Z"}}})
                boundary = "FundingRegistryBoundary"
                data = (f'--{boundary}\r\nContent-Disposition: form-data; name="query"; filename="query.json"\r\nContent-Type: application/json\r\n\r\n' + json.dumps(query) + f'\r\n--{boundary}--\r\n').encode()
                headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read(8_000_000)
                (out / f"{name}.txt").write_bytes(body)
                print(json.dumps({"name": name, "url": response.url, "status": response.status, "bytes": len(body)}))
        except (urllib.error.URLError, TimeoutError) as exc:
            print(json.dumps({"name": name, "error": str(exc)}))
