# Rahoitusrekisteri

Tampereen kaupungin ulkoisen rahoituksen keruu- ja tietokantaratkaisu. Sama Python-sovellus toimii paikallisesti SQLite-tietokannalla ja Microsoft Azuressa Azure SQL -tietokannalla. Päivittäinen keruu ei tarvitse kielimallia, maksullista hakupalvelua tai tämän keskustelun jatkumista.

**Toimitus sisältää ohjelmiston ja oikeasta julkisesta aineistosta kerätyn tietokannan. Kaupungin Azure-ympäristöön ei ole tehty käyttöönottoa eikä päivittäistä tuotantoajoa ole aktivoitu.** Toteutuneet testit ja lähteiden tila löytyvät [validointiraportista](docs/VALIDOINTI.md).

**Kokonaisuuden luovutus:** aloita [siirto- ja Azure-ohjeesta](docs/SIIRTO-JA-AZURE-ALOITUS.md). Se kertoo, mitä vastaanottaja tarvitsee Drivesta ja GitHubista sekä missä järjestyksessä Azure otetaan käyttöön.

## Kokeile heti

Pura siirtopaketti kokonaan. Sen juuressa ovat tämä ohje ja `rahoitusrekisteri.xlsx`; `data/funding.db` on valmis SQLite-tietokanta. `data/opportunities.csv` ja `data/opportunities.jsonl` ovat yleiskäyttöisiä taulukkovientejä. Mukana ovat myös `data/documents/`-kansion alkuperäistiedostot, kokotekstit ja hakukohtaiset asiakirjaluettelot. Varaa purkuun tilaa myös tälle aineistolle.

1. Avaa toimituksen Excel-poiminnan **Rahoittajat**-välilehti. Haut-välilehden suodattimilla voit rajata rahoittajaa, tietuetyyppiä (hakukierros / rahoitusmuoto / ennakkotieto), rahoitusryhmää (01–12), kaskadihakuja (FSTP), ohjelmaa, hakutilaa, määräaikaa, aluetta ja tarkistustarvetta. Se on päivätty poiminta tietokannasta.
2. Tutustu lähteiden kattavuuteen. Automaattisesti luettu hakulista ja pelkkä rahoittajan sivumuutosten seuranta ovat eri asioita.
3. Kytke jatkuva käyttö [Microsoft-ohjeen](docs/MICROSOFT-KAYTTOONOTTO.md) mukaan. Power BI:hin ja Exceliin on mukana valmiit Power Query -kyselyt.

Kehittäjän paikallinen käynnistys projektikansiossa (Python 3.12+ ja uv):

```sh
uv sync --frozen --extra dev
uv run funding init
uv run uvicorn funding.api:create_app --factory --host 127.0.0.1 --port 8765 --no-proxy-headers
```

Avaa `http://127.0.0.1:8765/docs`. Valitse `/v1/opportunities` → **Try it out**, täytä esimerkiksi `funder=Sitra`, `record_kind=funding_scheme`, `programme=HORIZON` tai `theme=Ilmasto ja energia` ja suorita haku. `GET /v1/funders` näyttää rahoittajaluettelon tietuemäärineen, `GET /v1/facets` käytettävissä olevat luokitukset. Paikallinen tila sallii vain loopback-yhteydet.

Keruu ja tiedostovienti:

```sh
uv run funding daily --require-all
uv run funding health --check
uv run funding coverage
uv run funding export --out outputs/data
```

Yhden lähteen uusinta: `uv run funding collect --source haeavustuksia --require-all`. Ajot eivät monista samoja hakuja. Epäonnistuminen ei poista vanhaa aineistoa eikä sulje hakuja. Lopetuskoodi 2 ilmaisee puutteellisen keruun, jotta ajastus voi havaita sen.

## Ehdot ja liitteet

Hakuilmoitusten sisältösivut, erilliset ehto-osiot, hakukohtaiset EU-vastaukset ja löydetyt asiakirjat tallentuvat tietokantaan sekä avoimeen tiedostovientiin. **Ehtoaineiston kattavuus on oma tietonsa:** se voi olla kesken tai osittainen, vaikka haku löytyy hakuluettelosta. Excelissä näkyvät kattavuustila, latausvirheet ja tekstin poiminnan puutteet.

Lue [ehtoaineiston käyttö- ja kattavuusohje](docs/EHDOT-JA-LIITTEET.md). `GET /v1/opportunities/{id}/documents` listaa aineiston; `content_q` hakee ehtojen ja liitteiden kokotekstistä. Koneellisen keruun onnistuminen ei vahvista kaikkien mahdollisten ehtojen kattavuutta.

## Mitä tieto sisältää?

- Pysyvä tunniste, julkaisijan tunniste ja alkuperäinen lähdelinkki.
- Rahoittaja, ohjelma, instrumentti, kieli, kuvaus, hakutila ja määräajat vaiheineen.
- Tietuetyyppi: **hakukierros** (`call`), **rahoitusmuoto** (`funding_scheme`) tai **ennakkotieto** (`advance_information`). Säätiöiden toistuvat apurahat ja investointilainat löytyvät myös hakukierrosten välissä. Rahoitusmuodolle ei keksitä avoimen haun tilaa tai määräpäivää.
- Teema- ja aluetunnisteet sekä tieto siitä, perustuuko luokitus lähteeseen vai hakusanasääntöön.
- Rahoitusmäärän, tukiprosentin ja hakijakelpoisuuden kentät. Tuntemattomat arvot säilyvät tyhjinä.
- Ensimmäinen ja viimeisin havainto, lähteen terveystieto, versiot, lähdeaineisto ja muutosloki.
- Asiantuntijan erillinen arvio kaupungin hakukelpoisuudesta, roolista ja palvelualueesta. Arvioon vaaditaan lähdeviite. Lähteen muuttuessa arvio merkitään uudelleen tarkistettavaksi.

**Rekisteri on laaja ehdokasaineisto. Jokainen ilmoitus ei sovellu Tampereelle.** Kaupunki voi osallistua hakijana, osatoteuttajana, kumppanina tai välillisenä hyötyjänä. Aluetta tai hakukelpoisuutta ei päätellä automaattisesti pelkästä rahoittajan nimestä. Tukipäätöksistä tai hankintasopimuksista ei tehdä avointa rahoitushakua.

## Kattavuuden hallinta

Rakenteinen keruu lukee Haeavustuksia.fi:n julkisen hakulistan, EURA 2021:n julkisen aineiston sekä EU Funding & Tenders -rajapinnan. EU-aineisto ositetaan hakujen aloituspäivän perusteella, jotta palvelun 10 000 tietueen raja ei katkaise keruuta. EU:n jatkohaulla on oma tunniste, vaikka sen emohanke olisi sama.

Version **0.4.0** toimituksessa on **16 069 tietuetta**: 15 926 hakukierrosta, 140 rahoitusmuotoa ja 3 ennakkotietuetta. Lähteitä on 53: 42 tuottaa tietueita, 10 seuraa sivumuutoksia ja yksi on asiantuntijatuonnille. Historia ja tuntemattomassa tilassa olevat rahoitusmuodot sisältyvät lukuihin. Rahoittajaluettelon eri nimimuodot eivät ole vahvistettu määrä erillisiä organisaatioita.

**[Pyydetyt 12 rahoitusryhmää](docs/PRIORITEETTILÄHTEET.md)** sisältävät FSTP:n, OPH:n, YM/Varken, AKKE/MYR:n, elinvoimakeskukset, kolme Interreg-ohjelmaa, LVM/Traficomin, kolme EIT-yhteisöä, Akatemian ja BF:n tutkimuskumppanuudet, nimetyt säätiöt, pohjoismaiset rahoittajat sekä ELENAn ja Innovation Fundin. Myös Sitra ja kaikki aiemmat lähteet säilyvät mukana. **MYR:n kokouskohtainen sisältö on vielä katve**, koska julkinen päätöspalvelu ei vastannut. Varken vanha avustuslinkki ja muut virheet näkyvät lähteiden ja asiakirjojen tiloissa.

API:n `priority=1`…`priority=12` rajaa pyydetyn ryhmän ja `cascade=true` FSTP-haut olemassa olevasta EU-lähteestä. `GET /v1/priorities` näyttää määrät, toteutuksen ja katveet. Samat ryhmät näkyvät Excelin suodattimessa ja Aloita tästä -välilehden alaosassa. Microsoftin Power Query -malli käyttää samaa `config/priorities.json`-määritystä. [Kaikkien lähteiden kattavuus](docs/RAHOITTAJAT-JA-KATTAVUUS.md) näyttää lähdekohtaisen laajuuden.

Kaikkien rahoittajien ja ohjelmien asetukset löytyvät [lähderekisteristä](config/sources.json). Sivuseuranta tallentaa sisältömuutokset ja linkit tarkistusjonoon (`/v1/changes`, tapahtumat `source_changed` ja `source_discovered`). Se **ei** väitä poimineensa kaikkia sivuston hakuja. Kiinteitä rahoitusmuotosivuja kerättäessä seurataan myös rahoittajan koontisivua uusien ohjelmien löytämiseksi. Asiantuntija voi tuoda tarkistetun ilmoituksen JSONL-tiedostosta komennolla `funding import polku.jsonl`.

Kaikkien mahdollisten rahoituslähteiden täydellisyyttä ei voi todentaa yhdellä rajapinnalla. Siksi mukana on [kattavuus- ja ylläpitomalli](docs/TIETOMALLI-JA-YLLAPITO.md), jossa katveet, omistajuus ja lähteiden lisääminen ovat näkyviä. Uudet ohjelmakaudet eivät edellytä tietokannan uudelleenrakentamista.

## Microsoft ja jatkokehitys

- **Azure SQL** on suositeltu tuotannon tietokanta. SQL-näkymät sopivat Power BI:hin, Exceliin ja Fabriciin. Power Apps voi käyttää SQL-liitintä tai OpenAPI-rajapintaa.
- **Azure Container Apps Job** ajaa keruun päivittäin klo 03.00 UTC eli Suomessa talvella 05.00 ja kesällä 06.00. Ajastuksen käyttöönotto on erillinen julkaisuvaihe.
- **Entra ID** suojaa tuotannon API:n; hallitut identiteetit yhdistävät sovellukset SQL:ään ilman tietokantasalasanoja.
- **REST/OpenAPI, CSV ja JSONL** mahdollistavat käytön muuallakin. `funding transfer` siirtää koko relaatiotietokannan tyhjään, samaan skeemaversioon migroituun kohteeseen.
- Tekoäly voi lukea rajapinnan tietoja ja lähdeviitteitä. Mahdolliset luokitukset, suositukset ja upotukset voidaan toteuttaa erillisinä palveluina. Ne eivät muuta julkaisijan alkuperäistä tietoa.

Testit: `uv run pytest -q`. Linux-kontti: `docker build -t funding-registry:local .`. SQL Server -integraatiotesti: `bash scripts/test_sqlserver.sh` (Docker, erillinen testikontti) tai `bash scripts/test_sqlserver_build.sh` (testi rakennusvaiheessa ilman host-portteja). Jälkimmäisellä on testattu myös asiakirjojen ja kokotekstien siirto SQL Server 2022:een. Testikuvia ei käytetä tuotannossa. Riippuvuudet on lukittu tiedostoihin `uv.lock` ja `requirements.lock`.

Skeemaversio on **0007**. Aiempi 0001/0002-tietokanta päivittyy komennolla `funding init`; tietueet ja arviot säilyvät. Tyhjän SQL Server -tietokannan luettava skeema on `infra/schema-current.sql`. Tavallinen käyttöönotto käyttää Alembic-migraatioita.

`scripts/build_workbook.mjs` on toimituksen Excelin muotoilutyökalu, joka käyttää Codexin Artifact Tool -kirjastoa. Sitä ei tarvita päivittäiseen keruuseen tai Microsoft-käyttöön. Jatkuvasti päivittyvä Excel liitetään SQL-näkymiin mukana olevilla Power Query -kyselyillä. CSV/JSONL-vienti toimii pelkällä Python-sovelluksella.
