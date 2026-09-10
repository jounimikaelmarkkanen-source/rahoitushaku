"""Write release validation from the exported snapshot and completed local checks."""
import json
import re
from pathlib import Path

metrics = json.loads(Path("outputs/data/metrics.json").read_text(encoding="utf-8"))
coverage = metrics["document_coverage"]
workbook_data = json.loads(Path("tmp/workbook-data.json").read_text(encoding="utf-8"))
current_rows = [row for row in workbook_data["rows"] if row["effective_status"] in {"open", "forthcoming", "rolling"}]
current_without_issues = sum(row["content_state"] == "collected_unverified" for row in current_rows)
current_with_failures = sum(row["failed_document_count"] > 0 for row in current_rows)
current_with_limits = sum(row["limited_document_count"] > 0 for row in current_rows)
sitra_example = next(row for row in workbook_data["rows"] if row["id"] == "241fd160-a65b-59ab-a0c3-c4c2dad1afab")
smoke_rows = [json.loads(line) for line in Path("tmp/api-smoke-current.log").read_text().splitlines() if line.startswith("{")]
smoke_times = {row["path"]: row["seconds"] for row in smoke_rows if "path" in row}
sitra_seconds = smoke_times["/v1/opportunities?funder=Sitra&limit=1"]
fulltext_seconds = smoke_times["/v1/opportunities?content_q=omarahoitus&limit=1"]
priority_smoke = [json.loads(line) for line in Path("tmp/api-priority-smoke.log").read_text().splitlines() if line.startswith("{")]
priority_seconds = next(row["seconds"] for row in priority_smoke if row.get("path") == "/v1/priorities")
tests = re.findall(r"(\d+) passed", Path("tmp/tests-v04.log").read_text())[-1]
pdf = next(x for x in metrics["document_formats"] if x["media_type"] == "application/pdf")
faq_entries = sum(x["documents"] for x in metrics["documents_by_parser_state"] if x["parser"] == "eu_faq_source" and x["state"] == "fetched")
def number(value):
    return f"{value:,}".replace(",", " ")


states = {"collected_unverified": "Kerätty, tarkistamatta", "partial": "Osittainen", "in_progress": "Keruu kesken", "not_started": "Aloittamatta"}
state_rows = "\n".join(f"| {label} | {number(coverage['calls'].get(key,0))} |" for key,label in states.items())
document_rows = "\n".join(f"| {state} | {number(count)} |" for state,count in sorted(coverage["current_documents"].items()))
source_rows = "\n".join(f"| {name} | {number(count)} |" for name,count in sorted(metrics["by_source"].items()))
report = f"""# Toimituksen validointi

Ohjelmistoversio **0.4.0**, tietokantaskeema **0007**. Toimituksen tietokantapoiminta: **{metrics['as_of_utc']} UTC**. Tarkat koneelliset määrät ja tarkistussumma ovat `data/metrics.json`-tiedostossa.

**Kaupungin Azure-ympäristöön ei ole tehty käyttöönottoa eikä päivittäistä tuotantoajoa ole aktivoitu.** Ohjelmisto, tietokanta, alkuperäistiedostot, Power Query -kyselyt ja Azure-käyttöönoton määritykset sisältyvät pakettiin.

## Mitä paketti sisältää

Rekisterissä on **{number(metrics['opportunities'])} tietuetta**, joista {number(metrics['by_record_kind']['call'])} hakukierrosta, {number(metrics['by_record_kind']['funding_scheme'])} rahoitusmuotoa ja {metrics['by_record_kind']['advance_information']} ennakkotietuetta. Mukana on {metrics['funder_names']} rahoittajan nimimuotoa ja {metrics['source_count']} lähderekisterin merkintää. Näiden määrä ei vahvista Tampereen hakukelpoisuutta tai kaikkien mahdollisten rahoituslähteiden kattavuutta.

Asiakirja-arkistossa on **{number(coverage['originals'])} sisältöversiota**. Niihin kuuluu **{number(pdf['originals'])} PDF-tiedostoa; jäsennin tunnisti niistä {number(pdf['pages'] or 0)} sivua**. Mukana on myös HTML-sivuja, JSON-lähdevastauksia ja Office-asiakirjoja. Luku sisältää myös lähdevastauksia ja keruun metatietoa; se ei ole erillisten hakujen tai vain ehtodokumenttien lukumäärä.

EU:n hakukohtaisia kysymys–vastauksia on {number(faq_entries)}, ja niitä on yhdistetty täsmällisen hakutunnuksen perusteella {number(metrics['opportunities_with_faq'])} hakuun. Keruu on englanninkielinen. Ensimmäinen täysi FAQ-poiminta täsmäsi lähteen ilmoittamaan 12 540 tietueeseen, eikä sen ositus- tai sivutustarkistus löytänyt puuttuvia tietueita.

Lähdevastauksissa **{number(metrics['source_content_gaps']['eu_entries_without_published_body'])} EU-haun varsinainen sisältöteksti** ja **{number(metrics['source_content_gaps']['faq_entries_without_published_question_or_answer'])} FAQ-tietueen kysymys tai vastaus** puuttuu. Nämä ovat sisällöllisiä puutteita, vaikka itse API-tietue on saatu kokonaisena. Lisätietorajapintaa yritetään erikseen, ja puutetta ei peitetä onnistuneella HTTP-vastauksella.

Lisäksi **{number(metrics['source_content_gaps']['attachment_urls_returning_html'])} liiteosoitetta palautti tiedoston sijasta verkkosivun**, ja **{number(metrics['source_content_gaps']['details_redirecting_to_front_pages'])} lisätietolinkkiä ohjasi etusivulle**. Vastaus on arkistoitu, mutta pyydetty aineisto on merkitty puuttuvaksi. **{number(metrics['source_content_gaps']['rate_limit_deferred_documents'])} asiakirjaa odottaa palvelun pyyntörajoituksen jälkeistä yritystä**. Niitä ei lasketa kerätyiksi. Tauon päättymisaika säilyy asiakirjan tiedoissa.

Uudet ja laajennetut lähteet kerättiin 10.9.2026. Aiemmin kerättyjen muiden luetteloiden omat havaintoajat säilyvät tietokannassa; niitä ei muuteta uuden lähteen tai poiminnan ajankohdaksi. Ehtojen ja liitteiden latausajat ovat asiakirjakohtaisia. Arkistoidun tekstin korjaus tai OCR ei muuta lähteen havaintoaikaa uudeksi.

## Pyydetyt rahoitusryhmät

Kaikki 12 ryhmää on rekisteröity. [Ryhmäkohtainen raportti](PRIORITEETTILÄHTEET.md) näyttää määrät, alkuperäislähteet ja katveet. FSTP-suodatin käyttää nykyisen EU-liittimen julkaisijan tunnistetta. MYR:n kokouskohtainen sisältö jää puuttumaan julkisen päätöspalvelun yhteysvirheen vuoksi. Varken yhden vanhan sisältösivun 404 ei estä saman hakemiston muiden tietojen keruuta.

## Ehtoaineiston toteutunut kattavuus

Ajankohtaisia tietueita (avoin, tuleva tai jatkuva haku) on **{number(len(current_rows))}**. Näistä **{number(current_without_issues)}** on tilassa `Kerätty, tarkistamatta`; lopuilla on kirjattuja puutteita. Latausvirheitä on {number(current_with_failures)} ajankohtaisen tietueen aineistossa, ja keruuraja näkyy {number(current_with_limits)} tietueella. Nämä ryhmät voivat olla päällekkäisiä. Alkuperäinen asiakirja voi olla mukana kokonaisena, vaikka sen koneellisen tekstipoiminnan tarkistus on kesken.

Ajankohtaisten ja tuntemattomassa tilassa olevien hakujen keruurajojen sisällä on vielä **{number(metrics['source_content_gaps']['current_or_unknown_pending_documents'])} odottavaa asiakirjaa**. Tämä määrä ei sisällä keruurajalle jääviä viitteitä eikä jo virhetilaan päätyneitä latauksia. Historiakeruun jono säilyy erikseen jatkettavana. Näiden joukkojen valmistumista ei päätellä pelkästä onnistuneesta ohjelman ajosta.

Esimerkiksi [Sitran Tuottavuutta tekoälyllä -haun](https://www.sitra.fi/rahoitushaku/rahoitushaku-tuottavuutta-tekoalylla-valmennusta-julkiselle-sektorille-uudistumisen-tueksi/) lisätiedot sisältävät myös erillisen kysymys–vastausartikkelin, johon lähdesivu viittaa lyhyellä ”tässä artikkelissa” -linkillä. Viittauksen tunnistusta korjattiin ja vastaavat linkit tarkistettiin muista arkistoiduista lähteistä. Tälle haulle on nyt tallennettu {number(sitra_example['fetched_count'])} aineistoa; luettelossa on {number(sitra_example['document_count'])} viitettä. Mukana ovat myös rahoitussopimus, yleiset rahoitusehdot, hankesuunnitelmapohja ja yleisten ehtojen kautta löytynyt saavutettavuusohje. Hakukohtainen luettelo ja mahdolliset puutteet: `data/documents/calls/241fd160-a65b-59ab-a0c3-c4c2dad1afab.html`.

| Hakukohtainen tila | Tietueita |
|---|---:|
{state_rows}

`Kerätty, tarkistamatta` tarkoittaa, että löydettyjen, keruusäännön piiriin kuuluvien asiakirjojen nouto ja tekstipoiminta onnistuivat. **Se ei ole asiantuntijan vahvistus kaikkien ehtojen löytymisestä.** Osittainen aineisto voi sisältää alkuperäiset tiedostot kokonaisina, vaikka esimerkiksi PDF:n tyhjä sivu, kuvamuotoinen teksti tai Office-asettelu vaatii tarkistusta.

| Aktiivinen asiakirja keruurajan sisällä | Määrä |
|---|---:|
{document_rows}

Keruurajalle jäävät viitteet ovat erikseen näkyvissä. Kaikki onnistuneesti poimitut viitteet säilyvät `links.jsonl`-tiedostossa, myös seuraamatta jätetyt viitteet. Yksittäisen haun asiakirjamäärä ei kuvaa kaikkien mahdollisten lisätietojen kokonaismäärää.

Haeavustuksia.fi:stä luetaan kuusi hakuilmoituksen osiota sekä tarvittaessa viisi vakioehtojen osiota ja julkisen lomake-esikatselun neljä osiota. EURAsta luetaan koko hakuilmoitus. EU:sta säilytetään täydet API-sisältöversiot, niistä löytyvät asiakirjat ja hakukohtaiset FAQ-vastaukset. Sitra ja muut rahoittajat saavat hakusivujen ja asiakirjaviitteiden keruun. [Ehtoaineiston ohje](EHDOT-JA-LIITTEET.md) kuvaa tarkat rajat.

## Toteutuneet tarkistukset

| Tarkistus | Tulos |
|---|---|
| Python-testit | **{tests} testiä läpi**. Hakuliittimet, versiokäsittely, arviot, suodatus, migraatiot ja tietojen siirto. |
| Rahoitusryhmien testit | Kaikkien 12 ryhmän määrät täsmäävät paikallisessa HTTP-testissä tietokannan suoraan laskentaan. FSTP rajautuu julkaisijan tunnisteella; ennakkotieto erotetaan hausta. Väärä ryhmätunnus palauttaa 422. |
| Asiakirjatestit | Kokotekstin ja alkuperäisbittien säilyminen, latauksen tarkistussumma, syvät viitteet, poistuneet viitteet, keruurajat, keskeytettävä eräajo, 304-päivitys, HTTP-virheet ja virheellinen lähdelinkki. |
| OCR ja uudelleenpoiminta | PNG-kalenterien ja ohjelma-aluekuvien alkuperäiset, kuvapisteraja, OCR-laatumerkinnät, identtisen PDF:n poiminnan uudelleenkäyttö, suhteellisten linkkien oikea kohde ja havaintoaikojen säilyminen. Puuttuvia julkaisijan ehtoja ei muuteta onnistuneeksi poiminnaksi. |
| FAQ | Täsmälliset hakutunnuskytkennät, vastausten säilyminen sekä poistetun kytkennän poistuminen aktiivisesta aineistosta historia säilyttäen. |
| Ruff | Sovelluskoodi, testit, migraatiot ja Python-apuskriptit tarkistettu. |
| SQLite | `integrity_check=ok`, vierasavainvirheitä ei ole. Toimituspoiminta tehtiin kerääjän ollessa pysäytettynä. |
| Tietokannan siirto | SQLite → tyhjä SQLite: kaikkien taulujen sisältövertailu, myös binääriset alkuperäistiedostot ja yli 32 000 merkin Unicode-teksti. Ei-tyhjä kohde ja aktiivinen kerääjä estävät siirron. |
| SQL Server -skeema | 44 T-SQL-lausetta käännetty SQLAlchemylla. `NVARCHAR(MAX)` ja `VARBINARY(MAX)`. Tämä on käännöstarkistus. |
| SQL Server 2022 -integraatio | Oikeaa kertakäyttöistä SQL Server Developer -instanssia vasten: migraatiot, Unicode, desimaalit, suuret binäärit ja kokotekstit, FSTP- ja rahoitusryhmäsuodatus, ennakkotiedot, arviokonfliktit, muutosvirta ja SQLite → SQL Server -siirto läpäisivät testin. |
| Azure Bicep | Määritys kääntyy ilman virheitä tai varoituksia. Ei Azure-resurssien luontia tai tenantissa tehtyä testiä. |
| Linux-sovelluskuva | Version 0.4 Docker-kuva rakennettu Python 3.12:lla. Muuttumattoman ODBC 18- ja PDF/OCR-ympäristön fin/swe/eng-kielet tarkistettiin jo edellisessä toimituksessa erillisessä rakennusvaiheessa ilman verkkoyhteyttä. |
| Excel | Neljä välilehteä, {number(metrics['opportunities'])} hakuriviä, aidot päivämäärät, suodattimet, jäädytetyt otsikot, 12 ryhmän laskelmat ja suodatus, FSTP-suodatin, rahoittajalaskelmat ja asiakirjaluetteloiden linkit. Renderöinti ja rakennetarkistus suoritettu. |
| Hakukohtainen HTML-luettelo | Muuttumaton luettelopohja tarkistettiin edellisessä toimituksessa leveänä ja 390 pikselin puhelinnäkymänä. Ei vaakasuoraa ylivuotoa. Lähdetekstin HTML ei suoriudu luettelossa koodina. |
| Paikallinen HTTP-rajapinta | Version 0.4 ryhmät, FSTP ja ennakkotiedot tarkistettu koko aineistoa vasten. Aiemmassa toimituksessa testatut Sitra-suodatus ja ehtoaineiston kokotekstihaku sekä PDF-esimerkin 55 900 merkin kokoteksti ja 469 163 tavun alkuperäislatauksen SHA-256-täsmäytys säilyvät edellisen version havaintoina. |
| Tiedostovienti | Alkuperäiset tavut tarkistetaan SHA-256:lla, kokotekstit viedään ilman katkaisua. ZIP-paketille tehdään CRC-tarkistus ja tiedostokohtainen SHA-256-manifesti. |

Testikirjastot antoivat deprekaatiovaroituksia, mutta testit eivät epäonnistuneet. Testitulokset eivät korvaa rahoitusasiantuntijan sisällöllistä arviota.

Version 0.4 kaikkien 12 ryhmän koonti valmistui paikallisessa HTTP-testissä {priority_seconds:.2f} sekunnissa; määrät täsmäsivät suoraan tietokantavertailuun. Edellisen version paikallisessa mittauksessa Sitra-suodatus vei {sitra_seconds:.2f} sekuntia ja koko arkiston `content_q=omarahoitus`-haku {fulltext_seconds:.2f} sekuntia. Mittaus tehtiin kasvavalla aineistolla rinnakkaisen keruun aikana; se ei ole tuotannon suorituskykylupaus. Laaja kokotekstihaku lukee tekstit SQL-kyselyllä, joten kaupungin kapasiteetti- ja hakutestaus tehdään myös täydellä aineistolla. Nopeaa koko arkiston tekstihakua varten tarvitaan erillinen indeksointi. Microsoft-liitännöissä hakutietojen ja asiakirjatekstien taulut tuodaan erikseen.

Version 0.4 Power Query -ryhmämalli toimitetaan saman `config/priorities.json`-määrityksen käyttäjäksi. Power Queryn suoritus ja tietolähteiden päivitys eivät ole tässä ympäristössä testattavissa; kaupungin tenantissa tehtävä koeajo on edelleen tarpeen. API ja Excel on testattu erikseen, eikä tämä vahvista Power BI:n pilvipäivitystä.

## Puutteet ja tuotannon hyväksyntätesti

Pohjoismaiden ministerineuvoston `norden`-sivuseuranta palautti HTTP 403 -käyttöeston. Myös asiakirjoissa on lähdekohtaisia käyttöestoja, poistuneita URL-osoitteita ja sivuja, joiden sisältö ei avaudu julkisena tekstinä. Lomake-esikatselun saatavuus voi poiketa lähteen esikatselulipusta. Tällaisia vastauksia ei lasketa hakuehdoiksi. Puutteet näkyvät hakukohtaisessa luettelossa ja tietokannassa; ne eivät poista aiemmin tallennettua versiota.

**SQL Server -sovellusintegraatio onnistui.** Testi ajettiin SQL Server 2022 Developer -instanssilla, Python 3.12:lla ja ODBC 18:lla eristetyssä Linux-rakennusvaiheessa. Varsinaisesta testivaiheesta oli verkkoyhteys poistettu; host-portteja, tuotantodataa ja kaupungin tunnuksia ei käytetty. Testi käyttää keinotekoista aineistoa. Se todentaa tietotyypit, siirtotoiminnon ja sovelluksen SQL Server -käytön, mutta ei koko tuotantoaineiston kapasiteettia tai kaupungin Azure SQL -verkkoyhteyttä.

Kaupungin IT voi toistaa testin komennolla `bash scripts/test_sqlserver_build.sh` tai tavallisena konttitestinä komennolla `bash scripts/test_sqlserver.sh`. Tenantissa tehdään todellinen aineiston siirto Azure SQL:ään ja varmistetaan Entra-roolit, hallitut identiteetit, verkkoyhteydet, Power BI / Excel -liitäntä, ajastus, kapasiteetti ja palautus. Päivittäisen tuotantoajon aktivointi tehdään tämän jälkeen.

{sum(s['collection_level'] == 'page_changes' for s in workbook_data['sources'])} lähdettä on edelleen sivumuutosten seurannassa. Se ei ole sama asia kuin jokaisen niiden hakuilmoituksen rakenteinen poiminta. Uudet ohjelma- ja rahoittajakohtaiset liittimet sekä yksittäisten keruupuutteiden ratkaisu ovat jatkuvan ylläpidon työtä.

## Tallennus ja ylläpito

Tietokanta ja tiedostovienti sisältävät osin saman aineiston kahdessa siirrettävässä muodossa. Varaa purkuun tilaa ZIP-tiedoston lisäksi, ja seuraa arkiston kasvua. Alkuperäiset ovat pakattuina tietokannassa; tiedostoviennissä ne ovat alkuperäisessä tiedostomuodossaan. Useassa haussa käytettävä sama sisältöversio tallennetaan yhteisenä resurssina.

Keruu jatkaa keskeneräistä jonoa. Neljän linkkiaskeleen, 250 asiakirjan ja 40 MB verkkovastauksen rajat sekä OCR:n sivuraja ovat näkyviä rajoituksia. Päivittäinen ajo palauttaa puutteesta ei-nollan lopetuskoodin, kun `--require-all` on käytössä. Ylläpidon tulee erottaa tekniset virheet, arkiston luonnolliset katveet ja asiantuntijaa edellyttävät tekstintunnistuksen tarkistukset.

## Lähdekohtaiset tietuemäärät

| Lähde | Tietueita |
|---|---:|
{source_rows}
"""
Path("docs/VALIDOINTI.md").write_text(report, encoding="utf-8")
print(json.dumps({"validation_report":"docs/VALIDOINTI.md","tests":int(tests),"snapshot":metrics["as_of_utc"]}))
