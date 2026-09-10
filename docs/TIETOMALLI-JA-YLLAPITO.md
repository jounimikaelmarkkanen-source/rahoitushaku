# Tietomalli, kattavuus ja ylläpito

## Tiedon periaatteet

Rekisterin perusyksikkö on **yksittäinen hakuilmoitus tai tunnistettava rahoitusinstrumentti**. Sama hankkeen emätunniste ei riitä yhdistämään erillisiä jatkohakuja. URL normalisoidaan ja siitä muodostetaan pysyvä UUID; julkaisijan tunniste säilytetään erikseen. Saman lähteen URL-muutoksissa alkuperäinen tunniste säilyy. Pelkkä samankaltainen otsikko ei yhdistä hakuja.

Rahoittajan tieto, sääntöpohjainen teematunniste ja kaupungin asiantuntija-arvio säilyvät erillisinä. Hakijakelpoisuutta ei vahvisteta kielimallilla eikä hakusanoilla. Uusi lähdeversio tekee vanhasta arviosta tarkistettavan. Alueen ulkopuolisia tai tuntemattomalla alueella olevia ilmoituksia säilytetään myös kumppanuuksien arviointiin.

## Taulut ja liitokset

| Taulu | Sisältö ja yhteys |
|---|---|
| `opportunities` | Yksi hakukierros, rahoitusmuoto tai ennakkotieto (`record_kind`); pysyvä `id`, ohjelma, lähde, tila, päivät, raha- ja laatukentät. |
| `sources` | Lähteiden asetukset, omistajuus, kattavuus, viimeinen yritys ja onnistuminen. |
| `source_items` | Julkaisijan tunnisteen yhteys hakuun ja viimeisin alkuperäinen JSON-aineisto. |
| `opportunity_tags` | Haun teemat, alueet ja muut tunnisteet. `basis=source` tai `rule`. |
| `deadlines` | Kaikki ilmoitetut hakuvaiheet. Päivä, mahdollinen tarkka UTC-aika, alkuperäinen arvo ja aikavyöhyke. |
| `reviews` | Kaupungin kelpoisuusarvio, rooli, palvelualue, perustelu ja arvioijan tunniste. |
| `changes` | Muutosjärjestyksen tunniste, tapahtumalaji, lähde-/arvioversio ja todistusaineisto. |
| `collection_runs` | Lähdekohtaiset ajot, odotettu raakatietuemäärä, tallennetut haut, hylkäykset ja lopputila. |
| `page_snapshots` | Sivuseurannan teksti ja pakattu alkuperäinen HTML, sisältöhash ja havaintoajat. |
| `documents` | Hakukohtaisten sisältösivujen ja asiakirjojen URL:t, keruutila, tekstin poiminnan tila ja nykyinen sisältöversio. |
| `document_blobs` | Tarkistussummalla yksilöidyt alkuperäiset tiedostot kokonaisina gzip-binääreinä, kokoteksti ja poiminnan laatutiedot. |
| `document_versions` | Asiakirjan sisältöversiot ja kunkin version ensimmäinen ja viimeinen havainto. |
| `document_links` | Alkuperäisversion kaikki poimitut viitteet, niiden roolit ja tieto viitteen seuraamisesta. |
| `opportunity_documents` | Hakujen ja asiakirjojen suhteet, viitesyvyys, juuriasiakirjat ja keruun rajoitukset. |
| `rejected_items` | Jäsentämättä jäänyt lähdetietue ja syy. Ei katoa hiljaisesti. |
| `leases` | Määräaikainen keruulukko; kaatuneen kerääjän lukko vanhenee. |
| `alembic_version` | Tietokannan migraatioversio. |

`v_funding` yhdistää hakuilmoituksen, tuoreustiedot, asiantuntija-arvion ja ehtoaineiston tilan. `v_funding_tags` on suodatukseen sopiva liitostaulu. `v_source_health` näyttää lähdetilanteen raportointityökalulle. `v_document_coverage` laskee asiakirjakattavuuden, ja `v_funding_documents` yhdistää hakukytkennät, alkuperäisviitteet ja kokotekstin. Puuttuva rahamäärä ei ole nolla. `total_budget` tarkoittaa koko hakukierroksen budjettia; `grant_max` yksittäisen hakijan mahdollista enimmäistukea. Näitä ei saa vaihtaa keskenään tai summata Tampereen käytettävissä olevaksi rahaksi.

## Mitä keruu poimii nyt?

| Lähderyhmä | Poiminta | Rajaus |
|---|---|---|
| Haeavustuksia.fi | Kaikki julkisen listan sivut ja tilat; lisäksi kuusi hakuilmoituksen osiota ja tarvittaessa viisi vakioehtojen osiota, kieliversiot ja asiakirjaviitteet. | Julkisen käyttöliittymän käyttämä API; hakemuksia tai kirjautumista ei käsitellä. Hakukohtainen `content_state` näyttää ehtokeruun toteutuneen kattavuuden. |
| EURA 2021 | Julkinen hakulista sekä koko ilmoituskohtainen aineisto, EAKR/ESR+/JTF, rahoitustiedot, valintaperusteet ja asiakirjaviitteet. | Kaikki listalla olevat alueet säilyvät. Hakukohtainen `content_state` näyttää onnistuneet ja puuttuvat sisältöasiakirjat. |
| EU Funding & Tenders | Tyypit 1 ja 8, kaikki hakutilat, englanninkieliset tietueet; täydet sisältöversiot, ehdot, asiakirjaluettelot ja hakutunnukseen liitetyt FAQ-vastaukset. | Kansallisten toimistojen ja ohjelmasivustojen ulkopuoliset haut vaativat lisälähteitä. Hankintoja ja FAQ-tietueita ei tulkita avustuksiksi; FAQ on haun lisäaineistoa. Ohjelmakenttä sisältää tunnisteesta saatavan ohjelma-/hakuperheen koodin. |
| Sitra | Julkisen API:n kaikki suomenkieliset rahoitushaut, sivutus, hakuaika, ohjelma, tila ja koko sisältö myös avattavista osioista. | Julkaisijan julkinen WordPress-rajapinta, ei pysyvää palvelulupausta. Hakijakelpoisuus arvioidaan erikseen. |
| OPH, NordForsk, Nordic Innovation, EUCF | Hakulistojen kortit ja määräajat; erillinen ehtokeruu lukee hakusivut ja niiden asiakirjaviitteet. Sivutus seuraa todellista seuraava-linkkiä. | Identtiset toistetut kortit yhdistetään; ristiriita keskeyttää lähteen ja näkyy virheenä. Hankinnat ja pelkät akkreditoinnit ohitetaan määritellyin säännöin. Asiakirjakeruun puutteet näkyvät erikseen. |
| Business Finland ja Työsuojelurahasto | Rahoitusmuotoluettelot ja jokaisen kortin sisältösivu. | Rahoitusmuoto ei tarkoita juuri nyt avointa hakua. Business Finlandin eri tukityypit voivat sisältää sekä lainaa että avustusta; tuntematon/muu instrumentti tarkistetaan. |
| Säätiöt, Pohjoismainen kulttuuripiste, AKKE, maaseutu, EIB/ELENA ja NIB | Nimetyt rahoitusmuodot sisältösivuineen; lisäksi koontisivun muutosten seuranta. | Erilliset hakukierrokset eivät automaattisesti jäsenny päivämääräkentiksi. Uudet ohjelmalinkit menevät tarkistusjonoon. |
| Muut sivuseurannat | Lähdesivun sisältömuutos ja tarkistettavat linkit. | Ei sivuston syväindeksointia eikä lupausta kaikkien ilmoitusten rakenteisesta poiminnasta. |
| Asiantuntijatuonti | Validoidut JSONL-ilmoitukset lähdeviitteineen. | Asiantuntijan on tarkistettava tieto ja päivitysvastuu. |

Teemaluokitus perustuu avoimiin suomen- ja englanninkielisiin hakusanasääntöihin. Se helpottaa suodatusta, mutta ei kata kaikkia ilmaisuja eikä arvioi hankkeen soveltuvuutta. Erityisesti lyhyen otsikon perusteella luokiteltu haku voi jäädä ilman teemaa. Tuntematon arvo on näkyvä jatkotyön kohde.

`source_status` säilyttää julkaisijan tilan. `effective_status` huomioi vanhentuneen määräajan; esimerkiksi lähteen virheellinen "open" ei pidä vuoden 2023 hakua avoimena. Tarkka määräaika säilyy UTC-aikana, päivätarkkuuden tiedosta ei keksitä kellonaikaa. Määräaikasarake on viimeinen ilmoitettu vaihe: toisessa vaiheessa voi olla erillinen jatkoonpääsyn ehto.

`record_kind=call` tarkoittaa yksittäistä ilmoitusta, `funding_scheme` rahoitusreittiä. Rahoitusmuoto voi kuvata vuosittaista hakua, neuvoteltavaa lainaa tai ohjelmaa, jonka yksittäiset haut julkaistaan myöhemmin. Sen `source_status=unknown` on tarkoituksellinen: yleiseltä sivulta ei päätellä avointa kierrosta, eikä vuosiluvuttomaan hakuaikaan lisätä kuluvaa vuotta. Myös menneitä kierroksia kuvaava rahoitusmuoto säilyy suunnittelua varten. Tarkista aina lähteen ajankohtaiset ehdot ja mahdollinen hakutauko.

Kelpoisuusteksti voi olla hakusanoilla poimittu ote (`eligibility_excerpt_requires_review`). `description` säilyttää ensimmäisen poiminnan kuvauksen; `detail_level` ei kuvaa erillisen ehtokeruun kattavuutta. Täydet sisältötekstit ja alkuperäiset tiedostot ovat asiakirjatauluissa ja hakukohtaisessa tiedostopaketissa. Ote ei sisällä välttämättä kaikkia rajauksia. `GET /v1/funders` ryhmittelee lähteiden rahoittajanimet ja laskee tietuemäärät. Se ei yhdistä viranomaisten vanhoja ja uusia nimiä samaksi oikeushenkilöksi.

`record_kind=advance_information` erottaa esimerkiksi MYR:n valmistelutiedot, ministeriön asiakirjaseurannan ja hakukalenterin yksittäisistä hakukierroksista. Ennakkotiedolle ei päätellä avointa hakua yleiseltä sivulta. Päivämäärät poimitaan vain tunnistetuista hakuaikakentistä; lähteen kirjaimellinen CET/CEST-aikavyöhyke säilytetään myös silloin, kun se eroaa paikallisesta kesäajasta.

## Pyydetyt rahoitusryhmät

`config/priorities.json` määrittelee 12 ryhmää. Ryhmän `rules` on vaihtoehtojen lista (TAI); yhden vaihtoehdon kentät täyttyvät yhdessä (JA), ja kentän arvoista riittää yksi. Sallittuja kenttiä ovat lähde, rahoittaja, ohjelma, tietuetyyppi, otsikon merkkijono ja julkaisijan tunnisteen alku. Tyhjää tai tuntematonta sääntöä ei hyväksytä. Arvot välitetään SQL:ään sidottuina parametreina.

FSTP tunnistetaan yhdistelmästä `source_id=eu-funding` ja `external_id` alkaa `cascade:`. Se perustuu olemassa olevan liittimen EU-rahoitustyyppiin 8. Tekstiä mainitseva tavallinen haku ei muutu kaskadihauksi. Innovation Fundin varsinaiset haut rajataan `programme=INNOVFUND`, kun taas EIB:n ELENA ja PDA ovat erillisiä valmistelutuen tietueita.

`GET /v1/priorities` näyttää ryhmät, määrät, lähdetilat ja puutteet. `GET /v1/opportunities?priority=8` käyttää samaa määritystä. Ryhmät voivat limittyä eivätkä korvaa muita rahoittajia. Määritys on julkaistava sovelluksen ja Power Queryn mukana. Toimituksen `data/priority-memberships.jsonl` on päivätty liitostauluvienti; elävä SQL-kytkentä käyttää `PowerQuery-Priorities.m`-kyselyä ja samaa JSON-määritystä.

EIT Urban Mobilityn `wordpress_calls`-liitin lukee kaikki julkaistun hakulajin sivut ja täsmäyttää sivutuksen palvelun kokonaismäärään. Määräaika poimitaan varsinaisesta hakukentästä; myöhempi osallistumisen vahvistamisaika ei korvaa sitä. Climate KIC:n ja 28DIGITALin luettelot käyttävät korttipoimintaa, jossa hankintoja rajataan pois. Suomen Akatemialta luetaan nykyinen hakuluettelo. YM, Varke, Traficom ja elinvoimakeskukset täydentävät Haeavustuksia.fi:n kierroksia omilla rahoitusmuodoillaan. Yksittäinen rikkoutunut sisältösivu säilyy listatietueena ja näkyy lähteen osittaisena keruuna.

## Kattavuuden työjono

Tavoite on kasvattaa tunnistettujen lähteiden kattavuutta jatkuvasti. Mittaa erikseen 1) rekisteröidyt lähteet, 2) toimiva automaattinen listapoiminta, 3) toimiva sivuseuranta, 4) manuaaliset lähteet ja 5) tuoreet asiantuntija-arviot. **Näiden määristä ei lasketa prosenttia kaikista maailman rahoitusmahdollisuuksista**, koska kokonaismäärää ei tunneta.

Ensimmäiset laajennukset ylläpitäjälle:

1. Käsittele ehtokeruun näkyvät puutteet: poistuneet asiakirjat, pääsyrajoitukset, OCR-tarkistukset ja keruurajoihin päätyneet viitteet. Ehtojen, lisätietojen ja liitteiden keruu on toteutettu; täydellisyys vahvistetaan hakukohtaisesti.
2. Interreg-ohjelmien erilliset haut sekä säätiöiden erillishakujen automaattinen jäsentäminen. Poimi hakijatyypit, tukiprosentit ja euromäärät rakenteisiin kenttiin vain todennettavista lähteistä; säilytä tarkka asiakirja- ja versioviite.
3. Nyt lisättyjen kolmen EIT-yhteisön lisäksi muut EIT-yhteisöt, kaupunkimissio ja EU-kumppanuuksien omat haut. MYR:n kokouskohtaisen sisällön julkisen lukutavan varmistaminen.
4. Pirkanmaan paikalliset Leader-ryhmät, säätiöt, kansainväliset kaupunkiverkostot ja määräaikaiset kilpailut; tukikelpoisen alueen tarkistus.
5. Lahjoitukset, sponsorointi, neuvotellut investointilainat ja yrityskumppanuudet asiantuntijan vastuulla. Näistä ei ole kattavaa julkista hakulistaa. Myös Tampereen oma ulospäin myöntämä avustus pitää erottaa ulkoisen rahoituksen mahdollisuudesta.

Sivuseurannan ilmoitus voi tarkoittaa päättynyttä hakua, hakutaukoa tai tiedotetta. Muutos ei automaattisesti luo avointa hakua. `norden`-lähteen mahdollinen HTTP 403 näkyy käyttörajoituksena; sitä ei kierretä selaimen tunnisteella tai välityspalvelimella.

## Päivittäinen ja jatkuva ylläpito

**Päivittäin:** tarkista kokonaisajon onnistuminen, lähteiden virheet ja yli 36 tunnin ikä, uudet/päivitetyt haut sekä sivuseurannan muutokset. Käsittele lähiviikkojen määräajat ensin. Korjaa jäsentimen rikkoutuminen alkuperäistä testitietuetta vasten ja aja vain kyseinen lähde uudelleen.

**Viikoittain:** käsittele tarkistusjono. Vahvista kaupungin rooli ja hakukelpoisuus sekä tarvittava konsortio. Tallenna arvio lähdeviitteineen. Uusi versio ei saa poistaa tehtyä arviointityötä.

**Kuukausittain:** nimetty rahoitusasiantuntija käy läpi lähdekatveet ja kaupungin palvelualueiden tarpeet. Liitinten tekninen ylläpitäjä tarkistaa päättyvät ohjelmakaudet ja muuttuneet URL-osoitteet. Lähderiviltä löytyvä "nimettävä" ei tarkoita, että omistajuus olisi jo sovittu.

**Julkaisujen yhteydessä:** testaa tietomalli, live-liitin rajatulla otannalla, SQL-migraatio, palautus, käyttöoikeudet ja siirto. Suorita riippuvuuksien päivitykset hallitusti. Source registry on versionhallittava julkaisun osa; uusi lähde ei vaadi tietokannan tyhjennystä.

**Uuden rahoittajan lisääminen:** lisää `config/sources.json`-tiedostoon yksilöllinen lähdetunniste, virallinen HTTPS-osoite, sallittu palvelinnimi, vastuuhenkilö ja kattavuus. `funding_pages` lukee `pages`-listan rahoitusmuodot ja `watch_catalogue=true` seuraa koontisivua. `funder_catalogue` lukee kortit CSS-valitsimilla ja haluttaessa niiden sisältösivut sekä seuraa sivutusta. Määritä rahoituslaji ja kieli, varmista todellinen sisältörakenne testillä, aja `funding sync-sources` ja `funding collect --source TUNNISTE --require-all`. Uusi liitin ei saa merkitä tyhjää tai rikkoutunutta sivua onnistuneeksi keruuksi. Kattavampi lähdeluettelo ja lähdekohtaiset määrät ovat [rahoittajakartoituksessa](RAHOITTAJAT-JA-KATTAVUUS.md).

## Tekoälyn liittäminen

Lue tiedot REST-rajapinnasta tai rajatuista SQL-näkymistä omalla lukuidentiteetillä. Käytä `id`:tä liitosavaimena ja `changes.id`:tä päivityskursorina. Tallenna AI-tulokset erilliseen tauluun tai palveluun: `opportunity_id`, lähdeversio, malliversio, ajankohta ja ehdotuksen sisältö. Alkuperäinen hakuilmoitus ja asiantuntijan vahvistus säilyvät ensisijaisina tietoina.

Verkkotekstit ovat epäluotettavaa syötedataa. Ne eivät saa antaa agentille uusia toimintaohjeita tai oikeutta lähettää hakemuksia, viestejä tai muuttaa tietokantaa. Tämän keruuratkaisun perustoiminta ei käytä tekoälyä eikä lähetä kaupungin tietoja ulkoiselle mallipalvelulle.

## Lähteet

- [Valtiokonttori: Haeavustuksia.fi](https://www.valtiokonttori.fi/palvelut/valtionavustuspalvelut/haeavustuksia/)
- [Euroopan komissio: Funding & Tenders API](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis)
- [EURA 2021: julkiset hakuilmoitukset](https://eura2021.fi/hakuilmoitukset/)
- [Opetushallitus: kansallinen ja keskitetty Erasmus+-rahoitus](https://www.oph.fi/fi/ohjelmat/kaikki-erasmus-rahoitushakuohjeet-kootusti)
- Kaikkien rekisteröityjen täydentävien lähteiden alkuperäisosoitteet ovat `config/sources.json`-tiedostossa.
