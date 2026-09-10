"""Publish source and user-priority coverage from the exact delivery snapshot."""
import json
from pathlib import Path

data = json.loads(Path("tmp/workbook-data.json").read_text())
metrics = json.loads(Path("outputs/data/metrics.json").read_text())
sources = data["sources"]
by_id = {s["id"]: s for s in sources}
health = {"success": "Onnistui", "partial": "Osittainen", "failed": "Virhe", "not_run": "Ei ajettu"}


def num(value):
    return f"{value:,}".replace(",", " ")


def cell(value):
    return str(value).replace("|", " / ").replace("\n", " ")


def source_table(rows):
    return "\n".join(f"| [{cell(s['name'])}]({s['url']}) | {num(metrics['by_source'].get(s['id'], 0))} | "
                     f"{health.get(s['health'], s['health'])} | {cell(s['coverage'])} |" for s in rows)


structured = [s for s in sources if s["collection_level"] == "structured"]
watched = [s for s in sources if s["collection_level"] == "page_changes"]
groups = []
for p in data["priorities"]:
    refs = ", ".join(f"[{cell(by_id[s]['name'])}]({by_id[s]['url']})" for s in p["sources"] if s in by_id)
    issues = "; ".join(f"{by_id[s]['name']}: {health.get(by_id[s]['health'], by_id[s]['health'])}" for s in p["source_issues"])
    groups.append(f"| {p['id']} | {cell(p['name'])} | {num(p['records'])} | {p['calls']} / {p['schemes']} / {p['advance_information']} | "
                  f"{cell(p['note'])} {'**'+cell(issues)+'**' if issues else ''} {refs} |")

priority_report = f"""# Pyydetyt 12 rahoitusryhmää

Tarkistettu 10.9.2026. Taulukon määrät ovat toimituspoiminnasta **{metrics['as_of_utc']} UTC**. Kaikki 12 ryhmää on rekisteröity ja ne löytyvät Excelin `Rahoitusryhmät (01–12)` -suodattimesta sekä API:n `priority`-parametrista. Ryhmä sisältää myös päättyneitä kierroksia, rahoitusmuotoja ja ennakkotietoja. Määrä ei tarkoita kaupungille avoimia tai kelpoisuudeltaan vahvistettuja hakuja. Ryhmät voivat limittyä.

| Prioriteetti | Rahoitusreitti | Tietueita | Kierrokset / muodot / ennakkotiedot | Toteutus ja rajaus |
|---|---|---:|---:|---|
{chr(10).join(groups)}

## Mitä tarkistuksessa muuttui

FSTP-hakuja oli olemassa olevassa EU-keruussa jo **{num(data['priorities'][0]['records'])}**. Niille lisättiin julkaisijan rahoitustyyppiin perustuva suodatin ilman päällekkäistä keruuta. Rahoittajien omat lähteet täydentävät portaalien sisältöä; sama rahoitushaku voi esiintyä eri julkaisijoilla eikä otsikon samankaltaisuus yhdistä niitä automaattisesti.

ARA:n seuraaja on [Varke](https://www.varke.fi/fi/yhteisot-ja-yhtiot/avustukset-yhteisoille-ja-yhtioille). ELY-keskusten seuraajien [palveluluettelo](https://elinvoimakeskus.fi/palveluhaku) luetaan EURAsta erillään, ja vanhat Pirkanmaan ELY:n ilmoitukset säilyvät. Palveluluettelossa on myös muiden alueiden tukia: vastuuviranomainen ja kohdealue tarkistetaan hankekohtaisesti. [Traficomin tukiluettelo](https://www.traficom.fi/fi/tuet-ja-avustukset) ja [LVM:n valtionavustussivu](https://lvm.fi/valtionavustukset) ovat erilliset lähteet.

[Interreg Europe](https://www.interregeurope.eu/call-for-projects) ilmoittaa ohjelmakauden 2021–2027 rahoituksen olevan sidottu. [Baltic Sea Region](https://interreg-baltic.eu/gateway/) ilmoittaa, ettei avoimia hakuja ole. Ne säilyvät rahoitusmuotoina ehtoineen. [Central Balticin ohjelma-alue](https://centralbaltic.eu/programme/about-the-programme/programme-area/) ja [hakukalenteri](https://centralbaltic.eu/for-applicants/call-calendar/) kerätään erikseen. Kalenteri ja aluekartta sisältävät kuvamuotoista tietoa, jonka alkuperäinen ja tekstin poiminnan tila näkyvät asiakirjoissa. Kaupungin roolia tai kaikkien tulevien hakujen aluekelpoisuutta ei päätellä ohjelman nimestä.

[EIT Urban Mobilityn](https://www.eiturbanmobility.eu/join-us/call-for-proposals/) julkinen hakurajapinta kerättiin kaikilta sivuilta, myös suljetut hakukierrokset. [Climate KIC:n](https://www.climate-kic.org/get-involved/open-calls/) avoimet ja suljetut hakukortit sekä [28DIGITALin](https://28digital.eu/our-messages/calls-tenders) rahoitus- ja kiihdyttämöhaut kerätään omilta sivuilta. Osallistumismaksu, konsortion rakenne ja kaupungin rooli tarkistetaan ehdoista.

Business Finlandilta lisättiin rahoitusmuotojen rinnalle [veturiyritysten haastekilpailu 2026](https://www.businessfinland.fi/palvelut/rahoitus/haut/2026/veturiyritysten-haastekilpailu-2026/) ja [jatkuva kumppanuusrahoitushaku](https://www.businessfinland.fi/palvelut/rahoitus/haut/2024/veturiyritysten-kumppanuusrahoitushaku-co-innovation/). Päivä- ja tilakentät luetaan julkaistuilta sivuilta. Jatkuvan haun sivun teknistä päättymispäivää ei tulkita hakemisen määräajaksi.

Herlin on täsmennetty kahdeksi säätiöksi: [Tiina ja Antti Herlinin säätiö](https://tahsaatio.fi/saatio/tietoa-meista/) sekä [Riikka Herlinin säätiö](https://rhsaatio.fi/toiminta/apurahat/). TAH:n yleinen rahoitusmalli ei perustu kaikille avoimeen vuosihakuun; erillinen koulujen luontoretkituki on mukana omana reittinään ja vuoden 2026 kierroksena. Riikka Herlinin säätiön julkaistu vuoden 2027 projektitukihaku on mukana omana hakutietueenaan. [Pirkanmaan rahaston](https://skr.fi/tietoa-meista/maakuntarahastot/pirkanmaa/) nykyinen hakumenettely tarkistetaan alkuperäislähteestä. Vanhoja vuosikiertoja ei ole kovakoodattu tuleviksi hauiksi.

[ELENA](https://www.eib.org/en/products/advisory-services/elena/index), [Innovation Fundin PDA](https://www.eib.org/en/products/mandates-partnerships/innovation-fund/index.htm) ja EU-portaalin varsinaiset Innovation Fund -haut ovat eri tietueita. [Nefco](https://www.nefco.int/about/how-we-finance/) ei tarkoita automaattista tukea Tampereelle; sen hakija- ja toiminta-alueet poikkeavat muiden pohjoismaisten rahoittajien ehdoista.

## Näkyvät puutteet

**MYR:n kokouskohtaisia asiakirjoja ei ole saatu kokonaisuudessaan.** [Pirkanmaan liiton MYR-sivu](https://www.pirkanmaa.fi/pirkanmaan-liitto-ja-paatoksenteko/maakunnan-yhteistyoryhma/) ja ennakkotiedon tietue ovat mukana, mutta sen linkittämä julkinen päätöspalvelu katkaisi yhteyden. Päätöspalvelun oma lähde on virhetilassa. Kokouskohtaiset esityslistat ja liitteet jäävät ylläpidon tarkistusjonoon; tätä ei esitetä valmiina EAKR-ennakkotietojen poimintana.

Varken hakemistossa oleva vanha latausinfrastruktuurin avustuslinkki palautti 404-vastauksen. Hakemiston tiedot säilytettiin, muut tukimuodot kerättiin ja puuttuva sisältö merkittiin osittaiseksi. Pohjoismaiden ministerineuvoston aikaisempi käyttöesto on edelleen erillinen katve; se ei estä Nordic Innovationin, NordForskin tai Nefcon keruuta.

Myös lähteessä onnistunut hakulistan poiminta voi sisältää keskeneräisen ehtoaineiston. Tarkista `content_state`, virheet, alkuperäistiedostot ja viitesyvyys. Kaikkien mahdollisten ehtojen täydellisyyttä ei ole vahvistettu. Toteutunut asiakirjakattavuus ja testitulokset ovat [validointiraportissa](VALIDOINTI.md).

## Käyttö

Excel: Haut-välilehden `Rahoitusryhmät (01–12)` ja `Kaskadihaku (FSTP)`; Aloita tästä -välilehden alaosassa ryhmien koonti. API: `/v1/opportunities?priority=1`, `?cascade=true`, `?priority=9&record_kind=call` ja `/v1/priorities`. Suodattimiin voi yhdistää esimerkiksi tilan, rahoittajan, teeman ja ehtoaineiston puutteet.

Microsoft: `PowerQuery-AzureSQL.m` sisältää `cascade`-sarakkeen. `PowerQuery-Priorities.m` muodostaa ryhmäjäsenyydet elävästä SQL-aineistosta käyttäen samaa `config/priorities.json`-tiedostoa kuin API. Power Query -malli ja tenantin päivitysasetukset on vielä testattava kaupungin ympäristössä. Päivätyssä viennissä jäsenyydet ovat `data/priority-memberships.jsonl` ja ryhmien tilat `data/priorities.json`. [Microsoft-ohje](MICROSOFT-KAYTTOONOTTO.md) kuvaa liitokset ja käyttöönoton.
"""
Path("docs/PRIORITEETTILÄHTEET.md").write_text(priority_report)

report = f"""# Rahoittajat ja keruun kattavuus

Toimituspoiminta **{metrics['as_of_utc']} UTC**. Rekisterissä on **{num(metrics['opportunities'])} tietuetta**: {num(metrics['by_record_kind']['call'])} hakukierrosta, {num(metrics['by_record_kind']['funding_scheme'])} rahoitusmuotoa ja {metrics['by_record_kind']['advance_information']} ennakkotietuetta. Rahoittajaluettelossa on {metrics['funder_names']} nimimuotoa. Nämä eivät ole kelpoisuudeltaan vahvistettujen rahoittajien tai avoimien hakujen määriä.

Lähteitä on {len(sources)}: {len(structured)} tuottaa tietueita, {len(watched)} seuraa sivumuutoksia ja yksi on asiantuntijatuontia varten. Versio 0.4 lisää edelliseen 15 752 tietueen aineistoon 317 tietuetta ja 15 lähdemääritystä. Viisi aiempaa sivuseurantaa tuottaa nyt myös tietueita. Vanha 1 996 ilmoituksen kuvakaappaus ei kuvaa tämän toimituksen laajuutta.

**[Pyydettyjen 12 rahoitusryhmän toteutus ja katveet](PRIORITEETTILÄHTEET.md)** näyttää ryhmäkohtaisen kattavuuden, linkit ja suodattimet. Sitra, muut säätiöt, ministeriöt, kaupunkiohjelmat ja aiemmat lähteet säilyvät mukana; aineistoa ei rajattu vain näihin 12 ryhmään.

Tietueita tuottavat lähteet keräävät hakukortit tai nimetyt rahoitusmuotosivut. Erillinen ehtokeruu syventää sisältöä: sisältösivut, ehdoista löytyvät lisätiedot ja alkuperäiset liitteet arkistoidaan hakukohtaisesti. [Ehtoaineiston ohje](EHDOT-JA-LIITTEET.md) kertoo rajat ja laatutilat. Lähteen onnistunut tila ei vahvista kaikkien ehtojen löytymistä.

## Tietueita tuottavat lähteet

| Lähde | Tietueita | Viimeisin ajo | Laajuus ja rajaus |
|---|---:|---|---|
{source_table(structured)}

## Sivumuutosten seuranta

Sivuseuranta tallentaa muutokset ja tarkistettavat linkit. Se ei luo automaattisesti kaikkia hakuilmoituksia eikä hakutauosta avointa hakua.

| Lähde | Hakutietueita | Viimeisin ajo | Seurannan kohde |
|---|---:|---|---|
{source_table(watched)}

## Päivittäinen ylläpito

`funding daily --require-all` lukee käytössä olevat lähteet ja jatkaa ehtoaineiston jonoa. Kiinteiden rahoitusmuotosivujen yhteydessä seurataan koontisivua uusien ohjelmien löytämiseksi. Virhe ei poista vanhaa tietoa eikä muuta sitä onnistuneeksi keruuksi. Havaintoajat ovat lähde- ja asiakirjakohtaisia; tämä poiminta ei muuta aiemmin kerättyjen luetteloiden päivää uudeksi.

Asiantuntija vahvistaa hakijan, alueen, konsortion, kaupungin roolin ja hankekohtaiset ehdot. Yritys- tai tutkimuspainotteinen rahoitus voi olla kumppanuuden kannalta hyödyllistä ilman kaupungin suoraa hakijakelpoisuutta. Uudet lähteet, rajaukset ja vastuut pidetään versionhallinnassa. [Ylläpitomalli](TIETOMALLI-JA-YLLAPITO.md) kuvaa lähteiden lisäämisen ja tarkistusjonon.

Kaikkien mahdollisten rahoitusreittien kokonaismäärää ei tunneta. Tuoreustieto, listapoiminta, sivuseuranta ja ehtoaineiston kattavuus mitataan erikseen. Päivittäistä tuotantoajoa ei ole aktivoitu kaupungin ympäristössä.
"""
Path("docs/RAHOITTAJAT-JA-KATTAVUUS.md").write_text(report)
print(json.dumps({"coverage_report": "docs/RAHOITTAJAT-JA-KATTAVUUS.md", "priority_report": "docs/PRIORITEETTILÄHTEET.md"}))
