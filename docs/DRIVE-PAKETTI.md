# Drive-paketin avaaminen

Drivessa käytetään tiedostoa **`rahoitusrekisteri-azure.zip`**. Se sisältää koko tietokannan alkuperäisine asiakirjoineen, koodin, Excelin, kokotekstit, taulukkoviennit, asiakirjaluettelot ja ohjeet. Tietokannassa on 47 298 alkuperäistä sisältöversiota. Erilliset alkuperäistiedostot palautetaan tarvittaessa alla olevalla komennolla; niiden samojen tavujen toinen kopio on jätetty pois ZIPistä siirron koon pienentämiseksi.

1. Lataa ZIP ja `rahoitusrekisteri-azure.sha256`. Tarkista SHA-256 ja pura koko ZIP.
2. **Azure SQL -siirrossa** käytä suoraan `data/funding.db`-tietokantaa [käyttöönotto-ohjeen](SIIRTO-JA-AZURE-ALOITUS.md) mukaan. Se sisältää myös kaikki alkuperäistiedostot, kokotekstit, versiot ja suhteet. Erillisten alkuperäistiedostojen palautusta ei tarvita SQL-siirtoa varten.
3. **Excelin offline-asiakirjalinkkejä varten** palauta alkuperäiset paketin juuresta alla olevilla komennoilla. Python 3.12+ ja uv tarvitaan. Komennot toimivat PowerShellissa sekä Linuxin ja macOS:n komentotulkissa.

```sh
uv sync --frozen
uv run python -c "from pathlib import Path; from sqlalchemy import create_engine; from funding.export import export_documents; print(export_documents(create_engine('sqlite:///data/funding.db'), Path('data')))"
```

Palautus lukee paikallista tietokantaa ja kirjoittaa `data/documents/`-kansioon alkuperäiset sekä niihin liittyvät viennit. Se ei tarvitse verkkokeruuta, muuta tietokantaa tai kaupungin Azure-oikeuksia. Alkuperäisten SHA-256 tarkistetaan palautuksen aikana. Riippuvuuksien ensimmäinen asennus tarvitsee verkkoyhteyden. Varaa koko aineiston käsittelyyn vähintään 80 GB työtilaa. Avaa tämän jälkeen `rahoitusrekisteri.xlsx` paketin juuresta.

`FILE-MANIFEST.json` kuvaa ZIPissä olevat tiedostot. `ORIGINALS-MANIFEST.json` kuvaa tietokannasta palautettavat alkuperäiset tarkistussummineen. `data/metrics.json` sisältää kaikkien tietokantataulujen määrät ja tietokannan SHA-256:n. Näitä käytetään luovutuksen ja Azure-siirron tarkistuksiin.

Kaikki alkuperäiseen toimitukseen kerätty data säilyy tässä muodossa. Ehtoaineiston tunnetut katveet ovat edelleen [validointiraportissa](VALIDOINTI.md); pakkaustavan muutos ei täydennä puuttuvia lähdesisältöjä.

Ylläpitäjä voi tehdä vastaavan siirtopaketin uudesta viennistä komennolla `python scripts/package_delivery.py --compact`. Tavallinen `python scripts/package_delivery.py` tekee suuremman täyspaketin, jossa alkuperäiset ovat lisäksi erillisinä tiedostoina.
