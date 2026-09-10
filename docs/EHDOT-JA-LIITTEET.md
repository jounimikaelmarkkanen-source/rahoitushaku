# Hakuehdot, lisätiedot ja alkuperäisaineisto

Hakuluettelo ei yksin ole riittävä ehtoaineisto. Rekisteri säilyttää nyt myös erilliset sisältösivut, ehtojen eri osiot, ohjeet, kysymys–vastaukset ja löydetyt asiakirjaviitteet. Jokaisen haun aineistolla on oma kattavuustila. **Automaattinen keruu ei vahvista, että kaikki mahdolliset ehdot on löydetty tai että Tampere on hakukelpoinen.**

## Aineiston avaaminen

Pura koko ZIP-paketti. Excelin **Haut**-välilehden oikeassa reunassa näkyvät ehtoaineiston tila, asiakirjamäärät ja puutteet. **Ehdot ja alkuperäistiedostot** avaa hakukohtaisen HTML-luettelon selaimessa. Samat luettelot ovat kansiossa `data/documents/calls/`, nimettyinä haun pysyvällä tunnisteella. Ne toimivat ilman erillistä palvelinta tai kirjautumista.

- `data/documents/originals/`: arkistoidut tiedostot. Tiedostonimen SHA-256-tunniste vastaa alkuperäistiedoston sisältöä.
- `data/documents/texts/`: erilliset kokotekstit, ilman tiivistämistä tai Excelin solupituuden katkaisua.
- `data/documents/documents.jsonl`: URL:t, noutotila, päivämäärät ja nykyinen sisältöversio.
- `data/documents/opportunity-documents.jsonl`: hakujen ja asiakirjojen suhteet, viitesyvyys, rooli ja rajaukset.
- `data/documents/links.jsonl`: lähdeversioista löydetyt linkit, myös viitteet joita keruusääntö ei seuraa.
- `data/documents/versions.jsonl` ja `contents.jsonl`: versiot, tarkistussummat, tiedostopolut ja tekstin poiminnan tila.

Microsoftissa `PowerQuery-Documents.m` tuo asiakirjat ja hakukytkennät. `PowerQuery-DocumentText.m` tuo kokotekstin numeroituina, enintään 16 000 merkin osina. Yhdistä taulut `document_id`-kentällä ja haut `opportunity_id`-kentällä. Pitkää asiakirjaa ei pidä kopioida yhteen Excel-soluun. SQL:n `v_funding_documents.full_text` ja API säilyttävät tekstin kokonaisena.

API:

```text
GET /v1/opportunities?content_state=partial
GET /v1/opportunities?content_q=omarahoitus
GET /v1/opportunities/{id}/documents
GET /v1/documents/{document_id}/text
GET /v1/documents/{document_id}/original
```

Tekstinäkymä palauttaa myös viitteet ja versiot. `sha256`-parametrilla voi lukea aiemman alkuperäisversion. Alkuperäistiedostot ladataan liitteinä; lähteiden HTML-koodia ei suoriteta API:n sivuna.

## Mitä kerätään syvemmältä

| Lähde | Hakukohtainen sisältö |
|---|---|
| Haeavustuksia.fi | Yleistiedot, hakuaika, perustiedot, myöntöperusteet, arviointiperusteet ja lisäehdot. Jos lähde ilmoittaa vakioehdot, myös niiden kaikki viisi julkista osiota. Esikatselukelpoisiksi ilmoitetuista hauista yritetään hakea lisäksi julkisen lomakepohjan neljä osiota. Jos palvelu ei julkaise esikatselua, se näkyy puutteena. Julkaistut kieliversiot ja tyhjät kentät säilyvät. |
| EURA 2021 | Koko julkinen hakuilmoitus esiladatusta lähdedatasta: kuvaus, muut tiedot, rahoitus, kustannusmallit ja valintaperusteet. Kokotekstiin otetaan ilmoituksessa käytettyjen koodien selitteet; alkuperäinen sivu sisältää myös lähteen koko koodiston. |
| EU Funding & Tenders | Aiemmin kerättyjen API-tietueiden täydet sisältöversiot: kuvaus, ehdot, päivitykset, lisätiedot, rahoitustiedot ja asiakirjaluettelot siinä laajuudessa kuin lähde julkaisee ne. Myös sisäkkäisiin JSON-kenttiin pakatut asiakirjaviitteet luetaan. |
| EU:n kysymys–vastaukset | Englanninkieliset kysymykset ja täydet vastaukset yhdistetään hakuihin täsmällisillä hakutunnuksilla, kuten portaalin hakukohtaisessa Q&A-näkymässä. Kyselyt ositetaan julkaisuajan mukaan alle 10 000 tuloksen rajan. |
| Sitra ja muut rahoittajat | Hakujen ja rahoitusmuotojen sisältösivut, niiden ehtoja, ohjeita ja lisätietoja koskevat viitteet sekä asiakirjaliitteet. |

Keruu lukee HTML-sisältöä myös avautuvista sisältöosioista ja `template`-elementeistä. PDF:n teksti luetaan kaikilta sivuilta ja PDF:n asiakirjaviitteet poimitaan. Jos sivulta löytyy alle 20 tekstimerkkiä, paikallinen OCR yrittää tunnistaa puuttuvan tekstin suomeksi, ruotsiksi ja englanniksi. Tämä ei havaitse varmasti kaikkia kuvina olevia tekstiosia. OCR merkitään aina tarkistettavaksi, ja alkuperäinen PDF säilyy muuttumattomana. Oletusraja on 100 OCR-sivua tiedostoa kohti (`FUNDING_OCR_MAX_PAGES`); rajan ylitys näkyy laatutiedoissa. Docker-kuvassa ovat tarvittavat OCR-ohjelmat. Office-tiedostosta säilytetään koko alkuperäinen tiedosto ja poimitaan XML-tekstisisältö; ulkoisia makroja, laskentaa tai upotettuja ohjelmia ei suoriteta.

EU:n hakutietue on arkistoitu alkuperäisestä API-tietueesta sarjallistettuna JSON-aineistona. Se ei ole verkkoliikenteen tavutasoinen tallenne. FAQ:n varsinaiset hakuvastaukset säilytetään myös kokonaisina sivuvastauksina. Keruun oma manifesti on merkitty erikseen keruun metatiedoksi.

Jos EU-haun sisältöteksti tai FAQ-vastaus puuttuu API-tietueesta, keruu yrittää lisäksi julkisen lisätietovastauksen. Tyhjä vastauskenttä jää puutteeksi myös silloin, kun rajapinta vastaa onnistuneesti. Lähteen julkaisemattomia tai poistamia vastauksia ei päätellä itse.

Lyhyt linkkiteksti, kuten ”tässä artikkelissa” tai ”here”, voi viitata varsinaisiin ehtoihin. Kerääjä hyödyntää tällöin myös linkin oman lyhyen kappaleen asiayhteyttä. Kysymys–vastaussivut tunnistetaan myös suomen-, ruotsin- ja englanninkielisistä URL-polkujen sanoista. Linkin yhteyteen tallennettu kappale auttaa tarkistamaan, miksi viitettä seurattiin.

## Kattavuustilat ja rajat

| Tila | Merkitys |
|---|---|
| `not_started` | Hakukohtaista asiakirjajonoa ei ole vielä muodostettu. |
| `in_progress` | Jonossa on vielä käsittelemätöntä aineistoa. |
| `partial` | Tiedostoa ei saatu, tekstin poiminta tarvitsee tarkistuksen tai keruuraja tuli vastaan. Osa tai kaikki alkuperäistiedostot voivat silti olla mukana. |
| `collected_unverified` | Muodostetun jonon asiakirjat on kerätty ja teksti poimittu ilman kirjattua ongelmaa. Kattavuutta ei ole vahvistettu asiantuntijatyönä. |

`detail_level` on vanhan hakulistapoiminnan kenttä. Se ei kerro ehtojen ja liitteiden kattavuutta. Käytä tähän `content_state`-kenttää ja asiakirjaluetteloa.

Excelin `Tallentamatta` ja SQL:n `pending_document_count` sisältävät myös keruurajalle jääviä viitteitä. `funding coverage` -raportin `current_documents` laskee vain aktiiviset, keruurajan sisällä olevat asiakirjat. Yksittäisen haun asiakirjamäärää ei pidä tulkita kaikkien mahdollisten lisätietojen kokonaismääräksi.

Oletus seuraa ehtoja ja asiakirjoja koskevia viitteitä neljän linkkiaskeleen päähän. Haulla käsitellään enintään 250 asiakirjaa; rajan saavuttaminen merkitään erikseen. Kaikki poimitut viitteet säilyvät lähdeversioiden yhteydessä. Rajaan jäävistä viitteistä näytetään rajausmerkintä; sen määrä ei ole arvio kaikkien puuttuvien tiedostojen lukumäärä. Yleinen navigaatio, sosiaalinen media ja kirjautumislinkit eivät kuulu ehtokeruuseen. Yksittäisen verkkovastauksen enimmäiskoko on 40 MB. Rajat ovat muutettavissa, mutta niitä ei saa tulkita täydellisyyden vahvistukseksi.

Skannaus, puuttuva PDF-teksti, Office-asettelu tai tuntematon tiedostomuoto näkyvät poiminnan laatutietona. Alkuperäinen tiedosto säilyy, vaikka koneellinen kokoteksti olisi puutteellinen. Julkaisija voi myös siirtää tai poistaa asiakirjan, julkaista lisäehdot myöhemmin tai vaatia kirjautumisen. Robots- ja pääsynrajoituksia noudatetaan. Epäonnistuminen ei poista aiemmin tallennettua versiota eikä sulje hakua.

Jos liitetiedoston URL palauttaa HTML-verkkosivun, kyseinen liite merkitään puuttuvaksi. Palvelun vastaus säilyy tarkistusta varten, mutta harhautuneen sivun linkkejä ei seurata tämän liitteen ehtoina. Sama verkkosivu voi olla itsessään kelvollinen sisältösivu toisessa yhteydessä; laatumerkintä koskee siksi URL-kohtaista asiakirjaa.

HTTP 429 -vastaus asettaa palveluosoitteelle yhteisen tauon. Kerääjä noudattaa `Retry-After`-aikaa sekunteina tai HTTP-päivämääränä; puuttuvan otsakkeen oletustauko on viisi minuuttia. Tauko ja seuraava yritysaika säilyvät tietokannassa. Tauon vuoksi tekemättä jäänyttä verkkopyyntöä ei kirjata tehdyksi latausyritykseksi. Avoinna olevien, jatkuvien ja tulevien hakujen asiakirjat käsitellään ensin.

Yksilöidyn lisätietopolun ohjautuminen sivuston etusivulle merkitään myös puutteeksi. Etusivua ei tulkita pyydetyksi ohjeeksi tai hakukohtaiseksi neuvontasisällöksi, eikä sen linkkejä seurata tämän haun lisätietoina. Palvelun vastaus säilyy tarkistettavana.

## Päivittäinen ajo ja täydentäminen

```sh
funding daily --require-all
funding coverage
```

Päivittäinen työ lukee hakulistat, kerää hakukohtaiset EU-vastaukset ja täydentää asiakirjat. Yksittäisen hakulähteen tai FAQ-keruun virhe ei ohita muun ehtoaineiston käsittelyä. Lähteiden tuoreus ja ehtoaineiston kattavuus valvotaan erikseen. Keskeneräinen työ jatkuu tietokantaan tallennetusta jonosta. Pitkän ajon yhteydessä keskiyön vaihtuminen ei käynnistä saman aineiston noutoa uudelleen.

```sh
funding enrich --source sitra
funding enrich --max-fetches 500
funding enrich --pending-only
funding enrich --pending-only --current-only
funding enrich --retry-failed
funding enrich --max-depth 5 --max-documents 500
funding faq
funding reextract --issues-only
```

`enrich` täydentää sisältösivut ja asiakirjaviitteet. `faq` täydentää EU:n Q&A-aineiston. `daily` tekee molemmat hakulistojen päivityksen jälkeen. `--max-fetches` on keskeytettävän eräajon työmääräraja; nolla tarkoittaa kaikkia erääntyneitä asiakirjoja. Se ei merkitse loppujonoa kerätyksi.

`--pending-only` käsittelee uudet jonossa olevat asiakirjat ilman jo ladatun aineiston päiväpäivitystä. `reextract` tekee kokotekstin ja OCR:n uudelleen arkistoiduista tiedostoista ilman verkkopyyntöjä. Se säilyttää alkuperäistiedoston ja lähteen todelliset havaintoajat. Jos korjattu poiminta löytää uusia viitteitä, `enrich --pending-only` hakee ne. `--parser eura` rajaa uudelleenpoiminnan esimerkiksi EURA-ilmoituksiin.

Yksittäinen poiminta voidaan korjata valitsimella `--document-id TUNNISTE`. Myös makroja tukevat `.xlsm`-, `.docm`- ja `.pptm`-liitteet kerätään. Niiden tiedostomuoto säilyy, ja tekstipoiminta lukee XML-sisällön suorittamatta makroja.

Jäsenninversio 5 tunnistaa myös ohjelmakäsikirjoihin, tukikelpoisuuteen ja hakukalentereihin johtavat lisätietoviitteet. Tunnistetut kalenteri- ja ohjelma-aluekuvat kerätään HTML:n kuvaviitteistä. PNG-alkuperäinen säilytetään; sen teksti luetaan Tesseractilla ja merkitään aina ihmisen tarkistettavaksi. Kuvaohjeen päivämääriä tai aluekelpoisuutta ei muuteta automaattisesti rakenteisiksi hakutiedoiksi. OCR rajataan 25 miljoonaan kuvapisteeseen ja 45 sekuntiin; rajan ylitys näkyy laatutiedossa. Päivitys ei automaattisesti poimi uudelleen koko vanhaa arkistoa: kohdenna `reextract` muuttuneisiin sisältöihin ja jatka sen jälkeen niiden linkkiketjuja.

Tiedosto ja sen kokoteksti ovat yhteisessä asiakirjarekisterissä. Sama yleinen ohjelmaohje voi kuulua monelle haulle, mutta se ladataan yhteisenä resurssina. Muuttuneesta alkuperäisaineistosta syntyy uusi tarkistussummalla yksilöity versio. Siihen liittyvien hakujen versiot muuttuvat ja aiemmat kelpoisuusarviot vaativat uuden tarkistuksen.

Alkuperäinen linkki ja latauksessa toteutunut osoite säilyvät erikseen (`url`, `final_url`). Pelkkä HTTP- ja HTTPS-linkkien vaihtelu ei muuta saman alkuperäistiedoston yhteisiä sisältötietoja eikä mitätöi muiden hakujen arvioita.

`--current-only` rajaa lataamisen ajankohtaisiin hakuihin ja hakuihin, joiden tila on vielä tuntematon. Päättyneet ja perutut haut jäävät historiakeruuseen. Tämä soveltuu ajankohtaisen aineiston linkkiketjujen täydentämiseen ilman koko vanhan arkiston läpikäyntiä. Jaetun ohjeen uudet viitteet päivittyvät myös sitä käyttäville historiatietueille, mutta niiden erillisiä tiedostoja ei ladata tässä rajatussa ajossa. Ilman valitsinta keruu käsittelee myös historian.

## Microsoft-siirto ja jatkokehitys

Kaikki aineisto on SQL-tietokannassa: alkuperäiset tiedostot gzip-pakattuina binäärikentissä, kokotekstit Unicode-tekstinä ja suhteet relaatiotauluina. Erillistä verkkolevyä tai tähän keskusteluun sidottua palvelua ei tarvita. `funding transfer` siirtää myös asiakirjat, versiot ja viitteet. Tiedostovienti on toinen, avoin jakelumuoto.

Azure SQL:ssä käytetään `VARBINARY(MAX)`- ja `NVARCHAR(MAX)`-tyyppejä. Alkuperäisten binäärien luku siirrossa tehdään yksitellen muistinkäytön rajaamiseksi. Paketti sisältää SQL-oikeudet myös uusille tauluille ja näkymille. Tekoälypalvelu voi myöhemmin indeksoida kokotekstit, mutta lähdetiedosto, sisältöversio ja mahdollinen puute tulee säilyttää mukana jokaisessa vastauksessa.

Microsoftin tekniset rajat ja tietotyypit: [Power BI:n tietotyypit](https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-data-types), [SQL Serverin suurten aineistojen tietotyypit](https://learn.microsoft.com/en-us/sql/t-sql/data-types/ntext-text-and-image-transact-sql?view=sql-server-ver17). Näihin liittyvät Power Query -kyselyt ja Azure-käyttöönotto on vielä testattava kaupungin omassa tenantissa.
