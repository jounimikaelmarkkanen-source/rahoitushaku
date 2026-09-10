import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const input = JSON.parse(await fs.readFile(process.argv[2] || 'tmp/workbook-data.json', 'utf8'));
const out = process.argv[3] || 'outputs';
await fs.mkdir(out, {recursive: true});
const wb = Workbook.create();
if (process.env.FUNDING_WORKBOOK_FORMULA_PROBE === '1') {
  const probe = wb.worksheets.add('Formula check');
  probe.getRange('A1:A3').values = [['01 First'],['02 Second'],['02 Second · 01 First']];
  probe.getRange('B1:B3').formulas = [['=COUNTIF(A1:A3,"01 First")'],['=COUNTIF(A1:A3,"02 Second · 01 First")'],['=COUNTIF(A1:A3,"01 First")+COUNTIF(A1:A3,"02 Second · 01 First")']];
  await wb.recalculate();
  console.log((await wb.inspect({kind:'region',sheetId:probe.name,range:'A1:B3',maxChars:2000,tableMaxRows:3,tableMaxCols:2})).ndjson);
  process.exit(0);
}
const home = wb.worksheets.add('Aloita tästä');
const calls = wb.worksheets.add('Haut');
const sources = wb.worksheets.add('Lähteet');
const funders = wb.worksheets.add('Rahoittajat');
const ink = '#163D49', muted = '#5C6D74', teal = '#087F8C';
const state = {open:'Avoin', forthcoming:'Tulossa', rolling:'Jatkuva', closed:'Päättynyt', unknown:'Tuntematon', cancelled:'Peruutettu'};
const scope = {eu:'EU', finland:'Valtakunnallinen', pirkanmaa:'Pirkanmaa', other_region:'Muu alue', unknown:'Ei tiedossa', international:'Kansainvälinen'};
const eligibility = {unreviewed:'Tarkistamatta', eligible:'Soveltuu', conditional:'Ehdollinen', ineligible:'Ei sovellu'};
const health = {success:'Onnistui', failed:'Virhe', partial:'Osittainen', not_run:'Ei ajettu'};
const content = {not_started:'Keruu aloittamatta',in_progress:'Keruu kesken',partial:'Osittainen',collected_unverified:'Kerätty, tarkistamatta'};
const kinds = {call:'Hakukierros',funding_scheme:'Rahoitusmuoto',advance_information:'Ennakkotieto'};
const priorityNames = Object.fromEntries(input.priorities.map(p=>[p.id,`${String(p.id).padStart(2,'0')} ${p.name}`]));
const instruments = {grant:'Avustus',loan:'Laina',guarantee:'Takaus',prize:'Palkinto',technical_assistance:'Valmistelun tuki',other:'Muu / tarkistettava'};
const rank = {open:0, rolling:1, forthcoming:2, unknown:3, closed:4, cancelled:5};
const rows = input.rows.sort((a,b) => rank[a.effective_status]-rank[b.effective_status] || (a.deadline_on||'9999').localeCompare(b.deadline_on||'9999') || a.title.localeCompare(b.title, 'fi'));
const last = rows.length+5;
const safe = value => {
  if (typeof value !== 'string') return value;
  const v = value.replace(/[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/gu, '');
  return /^\s*[=+@-]/.test(v) ? "'"+v : v;
};
const timestamp = value => value ? new Date(value.replace(' ','T')+(value.endsWith('Z')?'':'Z')) : null;
// Excel supports HYPERLINK; the authoring engine does not. Its verified fallback
// caches the real source URL instead of exporting an error value.
const link = (url,label='Avaa lähde') => `=IFERROR(HYPERLINK("${url.replaceAll('"','""')}","${label}"),"${url.replaceAll('"','""')}")`;

function base(sheet, address) {
  sheet.showGridLines = false;
  sheet.tabColor = teal;
  sheet.getRange(address).format.font = {name:'Calibri', size:11, color:'#243B43'};
  sheet.getRange(address).format.verticalAlignment = 'center';
}
function heading(sheet, title, subtitle, lastColumn) {
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = {size:23, bold:true, color:ink};
  sheet.getRange('A2').format.rowHeight = 38;
  sheet.getRange('A3').values = [[subtitle]];
  sheet.getRange('A3').format.font = {size:10, color:muted};
  sheet.getRange(`A5:${lastColumn}5`).format = {fill:ink, font:{bold:true,color:'#FFFFFF'}, wrapText:true, rowHeight:38};
}
function table(sheet, address, name) {
  const t = sheet.tables.add(address,true,name);
  t.style = 'TableStyleMedium2';
  t.showFilterButton = true;
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(1);
}

base(calls, `A1:Z${last}`);
const headers = ['Haku tai rahoitusmuoto','Ohjelma','Hakutila','Määräpäivä (viimeinen vaihe)','Rahoittaja','Alue','Teemat (hakusanasääntö)','Kelpoisuusarvio','Lähde','Lähteen tila','Alkuperäinen lähde','Pysyvä tunniste','Viimeksi havaittu (UTC)','Tarkistettava','Tietuetyyppi','Rahoituksen laji','Ehtoaineiston tila','Asiakirjoja','Tallennettu','Latausvirheitä','Tekstin tarkistuksia','Tallentamatta','Ehdot ja alkuperäistiedostot','Keruuraja saavutettu'];
headers.push('Rahoitusryhmät (01–12)','Kaskadihaku (FSTP)');
calls.getRange('A5:Z5').values = [headers];
const matrix = rows.map(r => [r.title, r.programme, state[r.effective_status], r.deadline_on ? new Date(r.deadline_on+'T00:00:00Z') : null, r.funder, scope[r.geographic_scope], r.themes, eligibility[r.eligibility], r.source_name, health[r.source_health]||r.source_health, null, r.id, timestamp(r.last_seen_at), r.needs_review ? 'Kyllä':'Ei',kinds[r.record_kind],instruments[r.instrument],content[r.content_state],r.document_count,r.fetched_count,r.failed_document_count,r.document_text_issues,r.pending_document_count,null,r.limited_document_count ? "Kyllä":"Ei"].map(safe));
matrix.forEach((row,i)=>row.push((rows[i].priorities||[]).map(id=>priorityNames[id]).join(' · ')||'Muut lähteet',rows[i].cascade?'Kyllä':'Ei'));
calls.getRange(`A6:Z${last}`).values = matrix;
calls.getRange(`K6:K${last}`).formulas = rows.map(r => [link(r.canonical_url)]);
calls.getRange(`W6:W${last}`).formulas = rows.map(r => [link(`data/documents/calls/${r.id}.html`,'Avaa ehtoaineisto')]);
calls.getRange(`D6:D${last}`).setNumberFormat('yyyy-mm-dd');
calls.getRange(`D6:D${last}`).format.horizontalAlignment = 'center';
calls.getRange(`M6:M${last}`).setNumberFormat('yyyy-mm-dd hh:mm');
calls.getRange(`A6:Z${last}`).format.wrapText = true;
const widths = [82,20,16,20,42,22,50,22,32,18,70,40,25,22,22,24,34,15,15,19,22,20,70,22,70,24];
widths.forEach((width,i) => calls.getRangeByIndexes(0,i,last,1).format.columnWidth = width);
matrix.forEach((r,i) => {
  const lines = Math.max(Math.ceil(rows[i].canonical_url.length/(widths[10]*0.92)), ...[0,1,4,5,6,8,24].map(j => Math.ceil(String(r[j]||'').length/(widths[j]*0.92))));
  calls.getRangeByIndexes(i+5,0,1,26).format.rowHeight = Math.max(34, lines*14+12);
});
table(calls, `A5:Z${last}`, 'FundingCalls');
heading(calls, 'Rahoitusmahdollisuudet', 'Suodata myös rahoitusryhmiä ja kaskadihakuja. Rahoitusmuoto ja ennakkotieto eivät ole avoimia hakuja.', 'Z');
calls.getRange(`K6:K${last}`).format.font.color = teal;
calls.getRange(`W6:W${last}`).format.font.color = teal;
calls.getRange(`R6:V${last}`).format.horizontalAlignment = 'center';
calls.getRange(`R6:V${last}`).setNumberFormat('#,##0');
calls.getRange(`C6:C${last}`).conditionalFormats.add('containsText',{text:'Avoin',format:{fill:'#E0F2EB',font:{color:'#16634A',bold:true}}});

const sourceLast = input.sources.length+5;
base(sources, `A1:J${sourceLast}`);
sources.getRange('A5:J5').values = [['Lähde','Poimintatapa','Tila','Viimeisin onnistuminen (UTC)','Ryhmä','Kattavuus ja rajoitukset','Lähdeviite','Lähteen tunniste','Automaattinen ajo','Viimeisin virhe']];
const level = {structured:'Tietueiden keruu',page_changes:'Sivumuutosten seuranta',manual:'Asiantuntijatuonti'};
sources.getRange(`A6:J${sourceLast}`).values = input.sources.map(s => [s.name,level[s.collection_level],health[s.health]||s.health,timestamp(s.last_success_at),s.category,s.coverage,null,s.id,s.enabled?'Käytössä':'Ei käytössä',s.last_error||''].map(safe));
sources.getRange(`G6:G${sourceLast}`).formulas = input.sources.map(s => [link(s.url)]);
sources.getRange(`D6:D${sourceLast}`).setNumberFormat('yyyy-mm-dd hh:mm');
sources.getRange(`D6:D${sourceLast}`).format.horizontalAlignment = 'center';
[42,26,17,27,22,88,65,24,22,75].forEach((width,i) => sources.getRangeByIndexes(0,i,sourceLast,1).format.columnWidth = width);
sources.getRange(`A6:J${sourceLast}`).format.wrapText = true;
sources.getRange(`A6:J${sourceLast}`).format.rowHeight = 86;
input.sources.forEach((s,i)=>{
  const lines=Math.max(Math.ceil(s.coverage.length/(88*0.9)),Math.ceil(s.url.length/(65*0.9)),Math.ceil((s.last_error||'').length/(75*0.9)));
  sources.getRangeByIndexes(i+5,0,1,10).format.rowHeight=Math.max(86,lines*14+16);
});
sources.getRange(`G6:G${sourceLast}`).format.font.color = teal;
table(sources, `A5:J${sourceLast}`, 'FundingSources');
heading(sources,'Lähteet ja kattavuus','Sivuseuranta tuottaa tarkistusjonon. Sen kaikkia hakuja ei ole poimittu hakutaulukkoon.','J');
sources.getRange(`C6:C${sourceLast}`).conditionalFormats.add('containsText',{text:'Virhe',format:{fill:'#FDECE6',font:{color:'#9B3522',bold:true}}});

const funderRows = input.funders.sort((a,b)=>a.funder.localeCompare(b.funder,'fi'));
const funderLast = funderRows.length+5;
base(funders, `A1:H${funderLast}`);
funders.getRange('A5:G5').values = [['Rahoittaja (lähteen nimimuoto)','Tietueita','Hakukierroksia','Rahoitusmuotoja','Avoin / tulossa / jatkuva','Tuntematon tila','Tietoja toimittavat lähteet']];
funders.getRange(`A6:G${funderLast}`).values = funderRows.map(f=>[safe(f.funder),null,null,null,null,null,safe([...new Set(rows.filter(r=>r.funder.toLowerCase()===f.funder.toLowerCase()).map(r=>r.source_name))].join(' · '))]);
for (let i=0;i<funderRows.length;i++) {
  const r=i+6, fr=`'Haut'!$E$6:$E$${last}`, kr=`'Haut'!$O$6:$O$${last}`, sr=`'Haut'!$C$6:$C$${last}`;
  funders.getRange(`B${r}:F${r}`).formulas = [[`=COUNTIF(${fr},A${r})`, `=COUNTIFS(${fr},A${r},${kr},"Hakukierros")`, `=COUNTIFS(${fr},A${r},${kr},"Rahoitusmuoto")`, ['Avoin','Tulossa','Jatkuva'].map(s=>`COUNTIFS(${fr},A${r},${sr},"${s}")`).join('+').replace(/^/,'='), `=COUNTIFS(${fr},A${r},${sr},"Tuntematon")`]];
  funders.getRange(`H${r}`).formulas = [[`=COUNTIFS(${fr},A${r},${kr},"Ennakkotieto")`]];
}
funders.getRange('H5').values = [['Ennakkotietueita']];
funders.getRange(`H1:H${funderLast}`).format.columnWidth = 22;
funders.getRange(`H6:H${funderLast}`).setNumberFormat('#,##0');
[55,16,18,20,23,20,65].forEach((width,i)=>funders.getRangeByIndexes(0,i,funderLast,1).format.columnWidth=width);
funders.getRange(`A6:H${funderLast}`).format.wrapText = true;
funders.getRange(`A6:H${funderLast}`).format.rowHeight = 60;
funders.getRange(`H6:H${funderLast}`).format.horizontalAlignment = 'center';
funders.getRange(`B6:F${funderLast}`).setNumberFormat('#,##0');
funders.getRange(`B6:F${funderLast}`).format.horizontalAlignment = 'center';
table(funders, `A5:H${funderLast}`, 'FundingOrganisations');
heading(funders,'Rahoittajat','Valitse rahoittaja Haut-välilehden suodattimesta. Nimimuodot tulevat julkaisijoilta; kelpoisuus tarkistetaan erikseen.','H');

base(home,'A1:C38');
home.getRange('A1:A38').format.columnWidth = 58;
home.getRange('B1:B38').format.columnWidth = 21;
home.getRange('C1:C38').format.columnWidth = 95;
home.getRange('A1:C38').format.wrapText = true;
home.getRange('A1:C38').format.rowHeight = 32;
home.getRange('A5:C12').values = [
 ['Aineisto','Ilmoituksia','Merkitys'],
 ['Kaikki tietueet',null,'Sisältää hakukierrokset, pysyvät rahoitusmuodot ja erikseen merkityt ennakkotiedot.'],
 ['Avoimet',null,'Hakutilan ja määräajan perusteella avoimet ehdokkaat.'],
 ['Tulevat',null,'Julkaistu ennakkoon tai hakuaika alkaa myöhemmin.'],
 ['Jatkuvat',null,'Lähteessä jatkuvaksi merkitty haku.'],
 ['Päättyneet',null,'Säilytetään historiaksi ja tulevien kierrosten tunnistamiseen.'],
 ['Tuntematon tila',null,'Hakutila tai ajallinen rajaus edellyttää tarkistusta.'],
 ['Peruutetut',null,'Lähteessä peruutetuksi merkitty haku.']
 ];
home.getRange('B6').formulas = [[`=COUNTA('Haut'!$A$6:$A$${last})`]];
home.getRange('B7:B12').formulas = ['Avoin','Tulossa','Jatkuva','Päättynyt','Tuntematon','Peruutettu'].map(s => [`=COUNTIF('Haut'!$C$6:$C$${last},"${s}")`]);
home.getRange('B6:B12').setNumberFormat('#,##0');
home.getRange('B6:B12').format.font = {bold:true,size:14,color:ink};
home.getRange('A13:C13').values = [['Rahoitusmuotoja',null,'Pysyviä rahoitusreittejä, myös hakukierrosten väliseen suunnitteluun. Tarkista ajankohtainen haku lähteestä.']];
home.getRange('B13').formulas = [[`=COUNTIF('Haut'!$O$6:$O$${last},"Rahoitusmuoto")`]];
home.getRange('B13').format.font = {bold:true,size:14,color:ink};
home.getRange('A13:C13').format.rowHeight = 46;
home.getRange('A14:C14').values = [['Ennakkotietueita',null,'MYR:n ja ministeriön valmisteluasiakirjat sekä ohjelmien hakukalenterit.']];
home.getRange('B14').formulas = [[`=COUNTIF('Haut'!$O$6:$O$${last},"Ennakkotieto")`]];
home.getRange('B14').format.font = {bold:true,size:14,color:ink};
home.getRange('B6:B28').format.horizontalAlignment = 'center';
home.getRange('A15').values = [['Näin käytät aineistoa']];
home.getRange('A16:C19').values = [
 ['1. Aloita Rahoittajat-välilehdeltä',null,'Näet rahoittajien nimet ja aineiston määrät. Etsi Sitraa, säätiöitä, ministeriöitä tai kansainvälisiä rahoittajia.'],
 ['2. Suodata Haut-välilehdellä',null,'Valitse rahoittaja, teema, alue, tietuetyyppi ja rahoitusryhmä. FSTP-hauille on oma Kaskadihaku-suodatin. Ryhmät on kuvattu tämän sivun alaosassa.'],
 ['3. Lue ehdot ja liitteet',null,'Haut-välilehden Ehdot ja alkuperäistiedostot avaa hakukohtaisen asiakirjaluettelon. Suodata myös ehtoaineiston tilaa ja latausvirheitä.'],
 ['4. Tallenna kaupungin arvio',null,'Arvio kirjataan rekisterin API:in. Exceliin tehdyt muutokset eivät päivity tietokantaan.']
 ];
home.getRange('A21').values = [['Kattavuus ja jatkuva käyttö']];
const sourceIssues = input.sources.filter(s => s.enabled && s.health !== 'success');
const sourceIssueText = sourceIssues.length ? sourceIssues.map(s=>s.name+': '+(health[s.health]||s.health)).join(' · ')+'. Tarkat virheet Lähteet-välilehdellä.' : 'Kaikki käytössä olevat lähteet vastasivat.';
home.getRange('A22:C28').values = [
 ['Tietueita tuottavia keruulähteitä',input.sources.filter(s=>s.collection_level==='structured').length,'Koontipalvelut sekä rahoittajien omat hakuluettelot, rahoitusmuodot ja erikseen merkityt ennakkotiedot.'],
 ['Täydentäviä sivuseurantoja',input.sources.filter(s=>s.collection_level==='page_changes').length,'Muutokset ja linkit tallentuvat rekisterin tarkistusjonoon. Hakujen rakenteinen poiminta vaatii lisäliittimiä.'],
 ['Lähteissä tarkistettavaa',sourceIssues.length,sourceIssueText],
 ['Päivittäinen tuotantoajo','Ei aktivoitu','Azure-käyttöönotto ja päivittäisen ajon aktivointi tehdään kaupungin Microsoft-ympäristössä.'],
 ['Ajantasainen Excel / Power BI',null,'Paketin Power Query -kyselyillä liitytään Azure SQL -näkymiin ja määritetään päivitysrytmi.'],
 ['Tampereen hakukelpoisuus','Tarkistettava','Aineisto on laaja ehdokasjoukko. Kaikki ilmoitukset eivät sovellu kaupungille.'],
 ['Poiminnan ajankohta',timestamp(input.created_at_utc),'UTC. Tämä tiedosto on päivätty poiminta; tietokanta säilyttää myös lähdeaineiston ja muutoshistorian.']
 ];
home.getRange('B28').setNumberFormat('yyyy-mm-dd hh:mm');
home.getRange('A16:C19').format.rowHeight = 46;
home.getRange('A22:C28').format.rowHeight = 46;
home.getRange('A24:C25').format.rowHeight = 60;
home.getRange('A24:C24').format.rowHeight = Math.max(60,Math.ceil(sourceIssueText.length/85)*14+12);
home.getRange('A15:C15').format.font = {bold:true,size:15,color:ink};
home.getRange('A21:C21').format.font = {bold:true,size:15,color:ink};
home.getRange('A24:C25').format.fill = '#FFF3E5';
heading(home,'Rahoitusrekisteri','Tampere • ulkoisen rahoituksen ehdokkaat ja lähdeseuranta','C');

home.getRange('A30').values = [['Ehdot, lisätiedot ja liitteet']];
home.getRange('A30:C30').format.font = {bold:true,size:15,color:ink};
home.getRange('A31:C36').values = [
 ['Aineisto kerätty, vielä tarkistamatta',null,'Löydetyt asiakirjaviitteet on kerätty. Tämä ei ole asiantuntijan vahvistus kaikkien ehtojen kattavuudesta.'],
 ['Osittainen aineisto',null,'Lataus, tekstin poiminta tai keruuraja edellyttää tarkistusta. Alkuperäistiedosto voi silti olla mukana kokonaisena.'],
 ['Keruu kesken',null,'Hakukohtainen jono sisältää vielä käsittelemättömiä asiakirjoja. Tarkat määrät näkyvät Haut-välilehdellä.'],
 ['Alkuperäistiedostot ja kokotekstit',null,'Pura koko ZIP-paketti. Hakukohtaiset luettelot ovat kansiossa data/documents/calls, tiedostot originals- ja texts-kansioissa.'],
 ['Pitkät ehdot Microsoftissa',null,'Power Query jakaa kokotekstin numeroituihin osiin. Lataa laajat asiakirjataulut tietomalliin tai rajaa ne ennen Exceliin lataamista.'],
 ['Keruun rajaukset',null,'Kirjautumista vaativa tai lähteen estämä aineisto merkitään puutteeksi. Tarkista myös alkuperäislähde ennen hakemista.']
];
home.getRange('B31:B33').formulas = ['Kerätty, tarkistamatta','Osittainen','Keruu kesken'].map(s => [`=COUNTIF('Haut'!$Q$6:$Q$${last},"${s}")`]);
home.getRange('B31:B33').setNumberFormat('#,##0');
home.getRange('B31:B33').format.font = {bold:true,size:14,color:ink};
home.getRange('B31:B33').format.horizontalAlignment = 'center';
home.getRange('A31:C36').format.rowHeight = 54;
home.getRange('A32:C33').format.fill = '#FFF3E5';
base(home,'A39:C56');
home.getRange('A39:C56').format.wrapText = true;
home.getRange('A39:C56').format.rowHeight = 38;
home.getRange('A39').values = [['Pyydetyt 12 rahoitusryhmää']];
home.getRange('A39:C39').format.font = {bold:true,size:15,color:ink};
home.getRange('A40:C40').values = [['Rahoitusryhmä','Tietueita','Kattavuus ja tarkistettavat asiat']];
home.getRange('A40:C40').format = {fill:ink,font:{bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:38};
for (let i=0;i<input.priorities.length;i++) {
  const p=input.priorities[i], r=i+41;
  const issues=p.source_status.filter(s=>p.source_issues.includes(s.id)).map(s=>`${s.name}: ${health[s.health]||s.health}${s.stale?', vanhentunut havainto':''}`);
  const note=p.note+(issues.length?' · '+issues.join(' · '):'');
  home.getRange(`A${r}:C${r}`).values = [[priorityNames[p.id],null,note]];
  // Exact combinations also cover overlapping groups. The authoring engine's
  // wildcard/array-text evaluation otherwise caches an incorrect zero.
  const combinations=[...new Set(rows.flatMap((row,index)=>(row.priorities||[]).includes(p.id)?[matrix[index][24]]:[]))];
  if (combinations.some(value=>value.length>255)) throw new Error('Priority labels exceed Excel COUNTIF criterion length');
  home.getRange(`B${r}`).formulas = [['='+(combinations.map(value=>`COUNTIF('Haut'!$Y$6:$Y$${last},"${value.replaceAll('"','""')}")`).join('+')||'0')]];
  home.getRange(`A${r}:C${r}`).format.rowHeight = Math.max(72,Math.ceil(note.length/84)*14+16,Math.ceil(priorityNames[p.id].length/50)*14+16);
  if (issues.length) home.getRange(`A${r}:C${r}`).format.fill = '#FFF3E5';
}
home.getRange('B41:B52').setNumberFormat('#,##0');
home.getRange('B41:B52').format.horizontalAlignment = 'center';
home.getRange('B41:B52').format.font = {bold:true,size:14,color:ink};
home.getRange('A54:C54').values = [['Ryhmät voivat limittyä',null,'Määrät sisältävät myös historian, rahoitusmuodot ja ennakkotiedot. Määrä ei vahvista hakukelpoisuutta tai kaikkien ehtojen kattavuutta.']];
home.getRange('A54:C54').format.rowHeight = 54;
await wb.recalculate();
console.log((await wb.inspect({kind:'region',sheetId:home.name,range:'A5:C12',maxChars:2500,tableMaxRows:8,tableMaxCols:3})).ndjson);
console.log((await wb.inspect({kind:'sheet,table',maxChars:2000,tableMaxRows:2,tableMaxCols:3})).ndjson);
for (const [sheetName,range,name] of [[home.name,'A1:C28','aloita'],[home.name,'A30:C36','ehtoaineisto'],[home.name,'A39:C46','rahoitusryhmat-1'],[home.name,'A47:C54','rahoitusryhmat-2'],[calls.name,'Y5:Z11','rahoitusryhmat-suodatus'],[calls.name,'Q5:X11','asiakirjat'],[calls.name,'A1:E10','haut'],[calls.name,'M5:P11','tietuetyyppi'],[sources.name,'A1:F9','lahteet'],[funders.name,'A1:H12','rahoittajat']]) {
  const png = await wb.render({sheetName,range,format:'png',scale:1.4});
  await fs.writeFile(`${out}/${name}-preview.png`,new Uint8Array(await png.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(`${out}/rahoitusrekisteri.xlsx`);
console.log(JSON.stringify({file:`${out}/rahoitusrekisteri.xlsx`,opportunities:rows.length,sources:input.sources.length}));
