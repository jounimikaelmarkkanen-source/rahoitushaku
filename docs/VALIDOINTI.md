# Toimituksen validointi

Ohjelmistoversio **0.4.0**, tietokantaskeema **0007**. Toimituksen tietokantapoiminta: **2026-09-10 05:56:33.516175 UTC**. Tarkat koneelliset määrät ja tarkistussumma ovat `data/metrics.json`-tiedostossa.

**Kaupungin Azure-ympäristöön ei ole tehty käyttöönottoa eikä päivittäistä tuotantoajoa ole aktivoitu.** Ohjelmisto, tietokanta, alkuperäistiedostot, Power Query -kyselyt ja Azure-käyttöönoton määritykset sisältyvät pakettiin.

## Mitä paketti sisältää

Rekisterissä on **16 069 tietuetta**, joista 15 926 hakukierrosta, 140 rahoitusmuotoa ja 3 ennakkotietuetta. Mukana on 116 rahoittajan nimimuotoa ja 53 lähderekisterin merkintää. Näiden määrä ei vahvista Tampereen hakukelpoisuutta tai kaikkien mahdollisten rahoituslähteiden kattavuutta.

Asiakirja-arkistossa on **47 298 sisältöversiota**. Niihin kuuluu **6 979 PDF-tiedostoa; jäsennin tunnisti niistä 254 533 sivua**. Mukana on myös HTML-sivuja, JSON-lähdevastauksia ja Office-asiakirjoja. Luku sisältää myös lähdevastauksia ja keruun metatietoa; se ei ole erillisten hakujen tai vain ehtodokumenttien lukumäärä.

EU:n hakukohtaisia kysymys–vastauksia on 12 540, ja niitä on yhdistetty täsmällisen hakutunnuksen perusteella 2 519 hakuun. Keruu on englanninkielinen. Ensimmäinen täysi FAQ-poiminta täsmäsi lähteen ilmoittamaan 12 540 tietueeseen, eikä sen ositus- tai sivutustarkistus löytänyt puuttuvia tietueita.

Lähdevastauksissa **15 EU-haun varsinainen sisältöteksti** ja **123 FAQ-tietueen kysymys tai vastaus** puuttuu. Nämä ovat sisällöllisiä puutteita, vaikka itse API-tietue on saatu kokonaisena. Lisätietorajapintaa yritetään erikseen, ja puutetta ei peitetä onnistuneella HTTP-vastauksella.

Lisäksi **290 liiteosoitetta palautti tiedoston sijasta verkkosivun**, ja **9 lisätietolinkkiä ohjasi etusivulle**. Vastaus on arkistoitu, mutta pyydetty aineisto on merkitty puuttuvaksi. **1 864 asiakirjaa odottaa palvelun pyyntörajoituksen jälkeistä yritystä**. Niitä ei lasketa kerätyiksi. Tauon päättymisaika säilyy asiakirjan tiedoissa.

Uudet ja laajennetut lähteet kerättiin 10.9.2026. Aiemmin kerättyjen muiden luetteloiden omat havaintoajat säilyvät tietokannassa; niitä ei muuteta uuden lähteen tai poiminnan ajankohdaksi. Ehtojen ja liitteiden latausajat ovat asiakirjakohtaisia. Arkistoidun tekstin korjaus tai OCR ei muuta lähteen havaintoaikaa uudeksi.

## Pyydetyt rahoitusryhmät

Kaikki 12 ryhmää on rekisteröity. [Ryhmäkohtainen raportti](PRIORITEETTILÄHTEET.md) näyttää määrät, alkuperäislähteet ja katveet. FSTP-suodatin käyttää nykyisen EU-liittimen julkaisijan tunnistetta. MYR:n kokouskohtainen sisältö jää puuttumaan julkisen päätöspalvelun yhteysvirheen vuoksi. Varken yhden vanhan sisältösivun 404 ei estä saman hakemiston muiden tietojen keruuta.

## Ehtoaineiston toteutunut kattavuus

Ajankohtaisia tietueita (avoin, tuleva tai jatkuva haku) on **970**. Näistä **153** on tilassa `Kerätty, tarkistamatta`; lopuilla on kirjattuja puutteita. Latausvirheitä on 735 ajankohtaisen tietueen aineistossa, ja keruuraja näkyy 708 tietueella. Nämä ryhmät voivat olla päällekkäisiä. Alkuperäinen asiakirja voi olla mukana kokonaisena, vaikka sen koneellisen tekstipoiminnan tarkistus on kesken.

Ajankohtaisten ja tuntemattomassa tilassa olevien hakujen keruurajojen sisällä on vielä **1 odottavaa asiakirjaa**. Tämä määrä ei sisällä keruurajalle jääviä viitteitä eikä jo virhetilaan päätyneitä latauksia. Historiakeruun jono säilyy erikseen jatkettavana. Näiden joukkojen valmistumista ei päätellä pelkästä onnistuneesta ohjelman ajosta.

Esimerkiksi [Sitran Tuottavuutta tekoälyllä -haun](https://www.sitra.fi/rahoitushaku/rahoitushaku-tuottavuutta-tekoalylla-valmennusta-julkiselle-sektorille-uudistumisen-tueksi/) lisätiedot sisältävät myös erillisen kysymys–vastausartikkelin, johon lähdesivu viittaa lyhyellä ”tässä artikkelissa” -linkillä. Viittauksen tunnistusta korjattiin ja vastaavat linkit tarkistettiin muista arkistoiduista lähteistä. Tälle haulle on nyt tallennettu 7 aineistoa; luettelossa on 8 viitettä. Mukana ovat myös rahoitussopimus, yleiset rahoitusehdot, hankesuunnitelmapohja ja yleisten ehtojen kautta löytynyt saavutettavuusohje. Hakukohtainen luettelo ja mahdolliset puutteet: `data/documents/calls/241fd160-a65b-59ab-a0c3-c4c2dad1afab.html`.

| Hakukohtainen tila | Tietueita |
|---|---:|
| Kerätty, tarkistamatta | 1 877 |
| Osittainen | 12 039 |
| Keruu kesken | 2 153 |
| Aloittamatta | 0 |

`Kerätty, tarkistamatta` tarkoittaa, että löydettyjen, keruusäännön piiriin kuuluvien asiakirjojen nouto ja tekstipoiminta onnistuivat. **Se ei ole asiantuntijan vahvistus kaikkien ehtojen löytymisestä.** Osittainen aineisto voi sisältää alkuperäiset tiedostot kokonaisina, vaikka esimerkiksi PDF:n tyhjä sivu, kuvamuotoinen teksti tai Office-asettelu vaatii tarkistusta.

| Aktiivinen asiakirja keruurajan sisällä | Määrä |
|---|---:|
| blocked | 460 |
| failed | 2 662 |
| fetched | 55 224 |
| pending | 27 815 |

Keruurajalle jäävät viitteet ovat erikseen näkyvissä. Kaikki onnistuneesti poimitut viitteet säilyvät `links.jsonl`-tiedostossa, myös seuraamatta jätetyt viitteet. Yksittäisen haun asiakirjamäärä ei kuvaa kaikkien mahdollisten lisätietojen kokonaismäärää.

Haeavustuksia.fi:stä luetaan kuusi hakuilmoituksen osiota sekä tarvittaessa viisi vakioehtojen osiota ja julkisen lomake-esikatselun neljä osiota. EURAsta luetaan koko hakuilmoitus. EU:sta säilytetään täydet API-sisältöversiot, niistä löytyvät asiakirjat ja hakukohtaiset FAQ-vastaukset. Sitra ja muut rahoittajat saavat hakusivujen ja asiakirjaviitteiden keruun. [Ehtoaineiston ohje](EHDOT-JA-LIITTEET.md) kuvaa tarkat rajat.

## Toteutuneet tarkistukset

| Tarkistus | Tulos |
|---|---|
| Python-testit | **75 testiä läpi**. Hakuliittimet, versiokäsittely, arviot, suodatus, migraatiot ja tietojen siirto. |
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
| Excel | Neljä välilehteä, 16 069 hakuriviä, aidot päivämäärät, suodattimet, jäädytetyt otsikot, 12 ryhmän laskelmat ja suodatus, FSTP-suodatin, rahoittajalaskelmat ja asiakirjaluetteloiden linkit. Renderöinti ja rakennetarkistus suoritettu. |
| Hakukohtainen HTML-luettelo | Muuttumaton luettelopohja tarkistettiin edellisessä toimituksessa leveänä ja 390 pikselin puhelinnäkymänä. Ei vaakasuoraa ylivuotoa. Lähdetekstin HTML ei suoriudu luettelossa koodina. |
| Paikallinen HTTP-rajapinta | Version 0.4 ryhmät, FSTP ja ennakkotiedot tarkistettu koko aineistoa vasten. Aiemmassa toimituksessa testatut Sitra-suodatus ja ehtoaineiston kokotekstihaku sekä PDF-esimerkin 55 900 merkin kokoteksti ja 469 163 tavun alkuperäislatauksen SHA-256-täsmäytys säilyvät edellisen version havaintoina. |
| Tiedostovienti | Alkuperäiset tavut tarkistetaan SHA-256:lla, kokotekstit viedään ilman katkaisua. ZIP-paketille tehdään CRC-tarkistus ja tiedostokohtainen SHA-256-manifesti. |

Testikirjastot antoivat deprekaatiovaroituksia, mutta testit eivät epäonnistuneet. Testitulokset eivät korvaa rahoitusasiantuntijan sisällöllistä arviota.

Version 0.4 kaikkien 12 ryhmän koonti valmistui paikallisessa HTTP-testissä 6.07 sekunnissa; määrät täsmäsivät suoraan tietokantavertailuun. Edellisen version paikallisessa mittauksessa Sitra-suodatus vei 8.06 sekuntia ja koko arkiston `content_q=omarahoitus`-haku 55.60 sekuntia. Mittaus tehtiin kasvavalla aineistolla rinnakkaisen keruun aikana; se ei ole tuotannon suorituskykylupaus. Laaja kokotekstihaku lukee tekstit SQL-kyselyllä, joten kaupungin kapasiteetti- ja hakutestaus tehdään myös täydellä aineistolla. Nopeaa koko arkiston tekstihakua varten tarvitaan erillinen indeksointi. Microsoft-liitännöissä hakutietojen ja asiakirjatekstien taulut tuodaan erikseen.

Version 0.4 Power Query -ryhmämalli toimitetaan saman `config/priorities.json`-määrityksen käyttäjäksi. Power Queryn suoritus ja tietolähteiden päivitys eivät ole tässä ympäristössä testattavissa; kaupungin tenantissa tehtävä koeajo on edelleen tarpeen. API ja Excel on testattu erikseen, eikä tämä vahvista Power BI:n pilvipäivitystä.

## Puutteet ja tuotannon hyväksyntätesti

Pohjoismaiden ministerineuvoston `norden`-sivuseuranta palautti HTTP 403 -käyttöeston. Myös asiakirjoissa on lähdekohtaisia käyttöestoja, poistuneita URL-osoitteita ja sivuja, joiden sisältö ei avaudu julkisena tekstinä. Lomake-esikatselun saatavuus voi poiketa lähteen esikatselulipusta. Tällaisia vastauksia ei lasketa hakuehdoiksi. Puutteet näkyvät hakukohtaisessa luettelossa ja tietokannassa; ne eivät poista aiemmin tallennettua versiota.

**SQL Server -sovellusintegraatio onnistui.** Testi ajettiin SQL Server 2022 Developer -instanssilla, Python 3.12:lla ja ODBC 18:lla eristetyssä Linux-rakennusvaiheessa. Varsinaisesta testivaiheesta oli verkkoyhteys poistettu; host-portteja, tuotantodataa ja kaupungin tunnuksia ei käytetty. Testi käyttää keinotekoista aineistoa. Se todentaa tietotyypit, siirtotoiminnon ja sovelluksen SQL Server -käytön, mutta ei koko tuotantoaineiston kapasiteettia tai kaupungin Azure SQL -verkkoyhteyttä.

Kaupungin IT voi toistaa testin komennolla `bash scripts/test_sqlserver_build.sh` tai tavallisena konttitestinä komennolla `bash scripts/test_sqlserver.sh`. Tenantissa tehdään todellinen aineiston siirto Azure SQL:ään ja varmistetaan Entra-roolit, hallitut identiteetit, verkkoyhteydet, Power BI / Excel -liitäntä, ajastus, kapasiteetti ja palautus. Päivittäisen tuotantoajon aktivointi tehdään tämän jälkeen.

10 lähdettä on edelleen sivumuutosten seurannassa. Se ei ole sama asia kuin jokaisen niiden hakuilmoituksen rakenteinen poiminta. Uudet ohjelma- ja rahoittajakohtaiset liittimet sekä yksittäisten keruupuutteiden ratkaisu ovat jatkuvan ylläpidon työtä.

## Tallennus ja ylläpito

Tietokanta ja tiedostovienti sisältävät osin saman aineiston kahdessa siirrettävässä muodossa. Varaa purkuun tilaa ZIP-tiedoston lisäksi, ja seuraa arkiston kasvua. Alkuperäiset ovat pakattuina tietokannassa; tiedostoviennissä ne ovat alkuperäisessä tiedostomuodossaan. Useassa haussa käytettävä sama sisältöversio tallennetaan yhteisenä resurssina.

Keruu jatkaa keskeneräistä jonoa. Neljän linkkiaskeleen, 250 asiakirjan ja 40 MB verkkovastauksen rajat sekä OCR:n sivuraja ovat näkyviä rajoituksia. Päivittäinen ajo palauttaa puutteesta ei-nollan lopetuskoodin, kun `--require-all` on käytössä. Ylläpidon tulee erottaa tekniset virheet, arkiston luonnolliset katveet ja asiantuntijaa edellyttävät tekstintunnistuksen tarkistukset.

## Lähdekohtaiset tietuemäärät

| Lähde | Tietueita |
|---|---:|
| aka | 9 |
| business-finland | 21 |
| business-finland-calls | 2 |
| central-baltic | 3 |
| eib | 2 |
| eib-elena | 1 |
| eit-climate | 111 |
| eit-digital | 9 |
| eit-urban | 91 |
| eu-funding | 11 328 |
| eucf | 8 |
| eura2021 | 1 040 |
| haeavustuksia | 2 615 |
| herlin-riikka | 2 |
| herlin-tah | 3 |
| innovation-fund-pda | 1 |
| interreg-baltic | 2 |
| interreg-europe | 2 |
| jane-atos | 1 |
| kone | 2 |
| kulturfonden | 1 |
| kuntasaatio | 1 |
| lvm | 1 |
| maaseutu | 1 |
| nefco | 1 |
| nessling | 3 |
| nib | 1 |
| nordforsk | 75 |
| nordic-culture | 8 |
| nordic-innovation | 40 |
| oph | 571 |
| pirkanmaa-akke | 1 |
| pirkanmaa-elinvoima | 47 |
| pirkanmaa-myr | 1 |
| sitra | 25 |
| skr | 1 |
| skr-pirkanmaa | 1 |
| traficom | 20 |
| tsr | 5 |
| varke | 7 |
| wihuri | 1 |
| ym | 4 |
