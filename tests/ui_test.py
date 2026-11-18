"""Автотест калькулятора TCO резервного живлення (index.html).

Запуск із кореня репозиторію:
    pip install playwright && python -m playwright install chromium
    python tests/ui_test.py            # або CHROME=/usr/bin/google-chrome python tests/ui_test.py

Скрипт сам піднімає локальний сервер на вільному порту і відкриває index.html у headless Chromium.
Код виходу 0 – усі перевірки пройшли, 1 – є провали.
"""
import json, re, os, sys, threading, functools, http.server, socketserver, tempfile
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
Handler = functools.partial(Quiet, directory=ROOT)
srv = socketserver.TCPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/index.html' % srv.server_address[1]
GOLDEN_LEADER = 'УЗЕ + PV + вітер – 13 653 669 грн'   # тестовий приклад, 10 років, ставка 0%
R = []
def ok(name, cond, info=''): R.append((name, bool(cond), info))
def start(b, vw=(1400, 1000)):
    ctx = b.new_context(viewport={'width': vw[0], 'height': vw[1]}, accept_downloads=True)
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append('console:' + m.text) if m.type == 'error' and '404' not in m.text and 'Failed to load resource' not in m.text else None)
    pg.goto(URL); pg.wait_for_timeout(1200)
    if pg.locator('#startok').is_visible():
        R.append(('стартове вікно ставить фокус на кнопку', pg.evaluate("document.activeElement.id") == 'startok', ''))
        pg.click('#startok')
    return ctx, pg, errs
def setv(pg, a, v):
    pg.click('[data-tab="p_in"]'); pg.evaluate("document.querySelectorAll('details.blk').forEach(d=>d.open=true)"); el = pg.locator(f'[data-in="{a}"]')
    if el.evaluate('e=>e.tagName') == 'SELECT': el.select_option(label=str(v))
    else: el.fill(str(v)); el.press('Tab')
    pg.wait_for_timeout(500)
def tco(pg): return re.sub(r'\s', ' ', pg.locator('#dA14').inner_text())
OVERLAP_JS = """(()=>{let n=0;document.querySelectorAll('#p_res svg').forEach(sv=>{const ts=Array.from(sv.querySelectorAll('text')).map(t=>t.getBoundingClientRect()).filter(r=>r.width>0);for(let i=0;i<ts.length;i++)for(let j=i+1;j<ts.length;j++){const a=ts[i],b=ts[j];if(a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1)n++;}});return n})()"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox'])
    ctx, pg, errs = start(b)
    ok('еталонний результат тестового прикладу', GOLDEN_LEADER in tco(pg), tco(pg)[:120])
    ok('версія в підвалі', re.search(r'версія \d', pg.locator('.fmain').inner_text()))
    # 1 structure
    pg.click('[data-tab="p_in"]')
    n_inputs=pg.evaluate("document.querySelectorAll('#inputs [data-in]').length")
    ids=pg.evaluate("Array.from(document.querySelectorAll('[id]')).map(e=>e.id)")
    dup=[i for i in set(ids) if ids.count(i)>1]
    ok('4 блоки',pg.locator('details.blk').count()==4)
    ok('усі блоки розгорнуті за замовчуванням',pg.evaluate("Array.from(document.querySelectorAll('details.blk')).every(d=>d.open)"))
    ok('поля вводу на місці',n_inputs>=150,f'{n_inputs} полів')
    ok('немає дубльованих id',not dup,str(dup))
    ok('Локація в блоці 1',pg.evaluate("!!document.querySelector('#blk1 #loc')"))
    ok('Режим відключень у блоці 3',pg.evaluate("!!document.querySelector('#blk3 #sched')"))
    ok('номерів полів немає',pg.locator('#inputs small').count()==0 and not pg.evaluate("Array.from(document.querySelectorAll('#inputs .row label, #inputs th.lab')).some(l=>/^\\s*\\d/.test(l.textContent) && !/^\\s*\\d+ /.test(l.textContent)===false && /^\\s*\\d{1,3}\\s*[А-ЯІЇЄA-Z]/.test(l.textContent))"))
    order=pg.evaluate("Array.from(document.querySelectorAll('details.blk>summary .bt')).map(e=>e.textContent)")
    ok('порядок блоків',order==['Об’єкт','Обладнання','Ускладнення','Економіка і різне'],str(order))
    # every input has non-empty label & hint
    bad=pg.evaluate("""Array.from(document.querySelectorAll('#inputs .row')).filter(r=>!r.querySelector('label').textContent.trim()||!r.querySelector('.hint').textContent.trim()).map(r=>r.id)""")
    ok('кожне поле має назву і підказку',not bad,str(bad))
    # 2 collapse/expand + nav
    pg.click('#blk2>summary'); pg.wait_for_timeout(200)
    ok('блок згортається',not pg.evaluate("document.getElementById('blk2').open"))
    pg.click('#blk2>summary'); pg.wait_for_timeout(200)
    ok('блок розгортається',pg.evaluate("document.getElementById('blk2').open"))
    pg.click('.secnav a[href="#blk4"]'); pg.wait_for_timeout(400)
    ok('кнопка переходу до блоку 4',pg.evaluate("Math.abs(document.getElementById('blk4').getBoundingClientRect().top)<200"))
    # 3 recalculation from each block
    base=tco(pg)
    for a,v in [('B6',400),('B24',700000),('B106',5),('B28',60)]:
        before=tco(pg); setv(pg,a,v); pg.click('[data-tab="p_res"]'); pg.wait_for_timeout(300)
        ok(f'зміна {a} перераховує результат',tco(pg)!=before)
    # 4 persistence
    pg.reload(); pg.wait_for_timeout(1500)
    pg.click('[data-tab="p_in"]')
    ok('значення зберігаються після перезавантаження',pg.locator('[data-in="B6"]').input_value()=='400' and pg.locator('[data-in="B28"]').input_value()=='60')
    ok('блоки знову розгорнуті після перезавантаження',pg.evaluate("Array.from(document.querySelectorAll('details.blk')).every(d=>d.open)"))
    # 5 export/import
    with pg.expect_download() as d: pg.click('#bsave')
    path=d.value.path(); data=json.load(open(path))
    ok('збереження проєкту у файл',data['inputs'].get('B28')==60)
    pg.click('#breset'); pg.wait_for_timeout(200); pg.click('.newopt[data-new=demo]'); pg.wait_for_timeout(600); pg.click('[data-tab="p_in"]')
    ok('«Новий проєкт» повертає типові значення',pg.locator('[data-in="B28"]').input_value()!='60')
    pg.set_input_files('#file',path); pg.wait_for_timeout(800)
    pg.click('[data-tab="p_in"]')
    ok('відкриття проєкту з файлу',pg.locator('[data-in="B28"]').input_value()=='60' and pg.evaluate("!!document.querySelector('#blk1 #loc') && !!document.querySelector('#blk3 #sched')"))
    # 6 sched mode switch stays in block 3
    pg.click('#sched input[value="schedule"]'); pg.wait_for_timeout(600)
    ok('режим «За графіком доби» відкривається в блоці 3',pg.evaluate("!!document.querySelector('#blk3 #sched [data-td]')"))
    pg.click('#sched input[value="shares"]'); pg.wait_for_timeout(400)
    # 7 checks -> jump with collapsed blocks
    cases=[('B6',0,'B6'),('B9',0,None),('B106',9,'B124'),('B43','150','B43'),('B87',95,'B87')]
    for a,v,expect in cases:
        setv(pg,a,v)
    pg.evaluate("document.querySelectorAll('details.blk').forEach(d=>d.open=false)")
    pg.click('[data-tab="p_chk"]'); pg.wait_for_timeout(300)
    rows=pg.locator('#checktable tr[data-go]')
    nrows=rows.count(); jumps=[]
    for k in range(nrows):
        pg.click('[data-tab="p_chk"]'); pg.wait_for_timeout(150)
        pg.evaluate("document.querySelectorAll('details.blk').forEach(d=>d.open=false)")
        r=pg.locator('#checktable tr[data-go]').nth(k); nm=r.locator('td').first.inner_text(); r.locator('.golink').click(); pg.wait_for_timeout(300)
        act=pg.evaluate("(()=>{const e=document.activeElement;const d=e&&e.closest('details');return [e&&e.getAttribute('data-in'), d?d.open:null, e?Math.round(e.getBoundingClientRect().top):null]})()")
        jumps.append((nm,act))
    good=[j for j in jumps if (j[1][0] and j[1][1] and 0<j[1][2]<1000) or (j[1][0] is None)]
    ok('«Перейти до поля» з кожної перевірки розгортає блок і ставить курсор',len(good)==len(jumps),'; '.join(f'{n}→{a}' for n,a in jumps))
    # 8 text scan for row numbers in all tabs
    allt=''
    for tab in ['p_res','p_in','p_chk','p_det','p_met']:
        pg.click(f'[data-tab="{tab}"]'); pg.wait_for_timeout(200)
        if tab=='p_in': pg.evaluate("document.querySelectorAll('details.blk').forEach(d=>d.open=true)")
        allt+=pg.locator(f'#{tab}').inner_text()+'\n'
    allt+=pg.evaluate("Array.from(document.querySelectorAll('#checktable td')).map(t=>t.textContent).join('\\n')")
    refs=[allt[max(0,m.start()-50):m.end()+10].replace('\n',' ') for m in re.finditer(r'(?i)\b(пол[еяіях]+|рядк\w*|рядок)\s+\d+',allt)]
    ok('ніде немає посилань «поле N»/«рядок N»',not refs,str(refs[:5]))
    ok('немає em dash',('—' not in allt))
    # 9 друк: згорнуті блоки розгортаються на час друку
    pg.click('[data-tab="p_in"]'); pg.evaluate("document.getElementById('blk2').open=false")
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    ok('друк розгортає згорнуті блоки', pg.evaluate("document.getElementById('blk2').open"))
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")
    ok('після друку блок знову згорнутий', not pg.evaluate("document.getElementById('blk2').open"))
    # 10 новий проєкт: порожній і тестовий приклад
    pg.click('#breset'); ok('«Новий проєкт» відкриває вибір', pg.locator('#newdlg').is_visible())
    pg.keyboard.press('Escape'); ok('Esc закриває вибір без змін', pg.locator('#newdlg').is_hidden())
    pg.click('#breset'); pg.click('.newopt[data-new=empty]'); pg.wait_for_timeout(600)
    ok('порожній проєкт: дані об’єкта порожні, константи типові', pg.locator('[data-in="B6"]').input_value() == '' and pg.locator('[data-in="B43"]').input_value() == '90')
    pg.click('[data-tab="p_res"]'); pg.wait_for_timeout(300)
    ok('порожній проєкт: замість нулів «Результату ще немає»', pg.locator('#resbody').is_hidden() and pg.locator('#resempty').is_visible())
    pg.click('#breset'); pg.click('.newopt[data-new=demo]'); pg.wait_for_timeout(600); pg.click('[data-tab="p_res"]')
    ok('тестовий приклад: результат знову видно і він еталонний', pg.locator('#resbody').is_visible() and GOLDEN_LEADER in tco(pg))
    # 11 горизонт 20 років
    setv(pg, 'B65', 20); pg.click('[data-tab="p_res"]'); pg.wait_for_timeout(400)
    ok('горизонт 20: заголовки показують 20 років', 'за 20 років' in tco(pg) and 'TCO 20 років' in pg.locator('#restable thead').inner_text())
    ok('горизонт 20: примітка про роки 11–20', pg.evaluate("!document.getElementById('hznote1').hidden && /11–20/.test(document.getElementById('hznote1').textContent)"))
    ok('горизонт 20: підписи графіків не перетинаються', pg.evaluate(OVERLAP_JS) == 0)
    pg.click('[data-tab="p_det"]'); pg.wait_for_timeout(300)
    ok('горизонт 20: таблиця по роках до 2046', '2046' in pg.locator('#t_cum').inner_text())
    setv(pg, 'B65', 10)
    # 12 дисконтування
    pg.click('[data-tab="p_res"]'); ok('ставка 0%: колонки NPV немає', 'NPV' not in pg.locator('#restable thead').inner_text())
    setv(pg, 'B90', 15); pg.click('[data-tab="p_res"]'); pg.wait_for_timeout(300)
    ok('ставка 15%: є колонка «TCO, NPV»', 'TCO, NPV при 15%' in pg.locator('#restable thead').inner_text())
    ok('ставка 15%: ефект позначено як дисконтований', 'дисконтованого' in pg.locator('#dA15').inner_text())
    setv(pg, 'B90', 0); pg.click('[data-tab="p_res"]')
    ok('ставка 0%: результат знову еталонний', GOLDEN_LEADER in tco(pg))
    # 13 файл попередньої версії
    with pg.expect_download() as d: pg.click('#bsave')
    o = json.load(open(d.value.path())); o['model'] = 'v11'; o['inputs'].pop('B65', None)
    f = os.path.join(tempfile.mkdtemp(), 'old.json'); json.dump(o, open(f, 'w'), ensure_ascii=False)
    pg.set_input_files('#file', f); pg.wait_for_timeout(800)
    m = pg.locator('#filemsg').inner_text()
    ok('файл попередньої версії: пояснення і нове поле', 'попередній версії' in m and '«Горизонт розрахунку»' in m, m[:120])
    # 15 QA 6.0: межі правдоподібності й неможливі значення
    def errs_of():
        return pg.evaluate("Array.from(document.querySelectorAll('#checktable tbody tr')).filter(r=>r.classList.contains('err')||r.classList.contains('warn')).map(r=>r.cells[0].textContent+'|'+(r.classList.contains('err')?'E':'W'))")
    pg.click('#breset'); pg.click('.newopt[data-new=demo]'); pg.wait_for_timeout(500)
    ok('тестовий приклад без помилок і попереджень', errs_of() == [], str(errs_of()))
    for a, v, name, lvl in [('B45', '50', 'Ресурс батареї в циклах', 'E'), ('B30', '1', 'Інтервал ТО генератора', 'E'),
                            ('B33', '10', 'Ресурс ДГ до капремонту', 'E'), ('B122', '1000', 'Власне споживання інвертора', 'W'),
                            ('B126', '0,01', 'Підвезення пального частіше ніж двічі на добу', 'W'), ('B106', '400', 'Блекаути довші за рік', 'E')]:
        old = pg.locator(f'[data-in="{a}"]').input_value(); setv(pg, a, v)
        ok(f'неправдоподібне {a}={v} → {name}', any(x == name + '|' + lvl for x in errs_of()), str(errs_of()))
        setv(pg, a, old)
    old = pg.locator('[data-in="B114"]').input_value(); setv(pg, 'B114', '95')
    ok('поріг заміни АКБ вище гарантії → попередження', any(x.startswith('Заміна батареї раніше за гарантію') for x in errs_of())); setv(pg, 'B114', old)
    olds = [pg.locator(f'[data-in="B{r}"]').input_value() for r in (15, 16, 17, 18)]
    for r in (15, 16, 17, 18): setv(pg, f'B{r}', '30')
    ok('сума днів сезонів 120 → помилка, результат схований', any(x == 'Сума днів сезонів|E' for x in errs_of()) and pg.locator('#resbody').is_hidden())
    pg.click('[data-tab="p_det"]'); ok('при помилках «Деталі» теж сховані', pg.locator('#detbody').is_hidden() and pg.locator('#detempty').is_visible())
    for r, v in zip((15, 16, 17, 18), olds): setv(pg, f'B{r}', v)
    # одиниці й роздільники в полях
    for v, exp in [('500 000 грн', '500000'), ('1.000,5', '1000,5'), ('1,000.5', '1000,5'), ('550000', '550000')]:
        setv(pg, 'B24', v); got = re.sub(r'\s', ' ', pg.locator('[data-in="B24"]').input_value())
        ok(f'поле приймає «{v}»', got == exp and not any(x.startswith('Параметри ДГ') for x in errs_of()), got)
    setv(pg, 'B24', 'abc')
    ok('текст у полі: помилка без хибного «ціна 0» і з aria-invalid', not any('дорівнює 0' in x for x in errs_of()) and pg.locator('[data-in="B24"]').get_attribute('aria-invalid') == 'true')
    setv(pg, 'B24', '550000')
    # діалоги і клавіатура
    pg.click('#breset'); seq = []
    for i in range(6): pg.keyboard.press('Tab'); seq.append(pg.evaluate("!!document.activeElement.closest('#newdlg')"))
    ok('фокус не виходить за межі вікна «Новий проєкт»', all(seq)); pg.keyboard.press('Escape')
    pg.focus('.tabs button[data-tab=p_res]'); pg.keyboard.press('ArrowRight')
    ok('вкладки перемикаються стрілками', pg.locator('#p_in').is_visible())
    # файли: новіша версія, сміття в списку, налаштування панелей
    with pg.expect_download() as d: pg.click('#bsave')
    good = json.load(open(d.value.path())); tmp = tempfile.mkdtemp()
    o = json.loads(json.dumps(good)); o['model'] = '99.0'; f1 = os.path.join(tmp, 'new.json'); json.dump(o, open(f1, 'w'))
    pg.set_input_files('#file', f1); pg.wait_for_timeout(600)
    ok('файл новішої версії: окреме повідомлення', 'новішій версії' in pg.locator('#filemsg').inner_text())
    o = json.loads(json.dumps(good)); o['inputs']['B65'] = 25; o['pvset'] = {'tilt': 'x', 'az': None, 'pr': -1}; f2 = os.path.join(tmp, 'bad.json'); json.dump(o, open(f2, 'w'))
    pg.set_input_files('#file', f2); pg.wait_for_timeout(600)
    ok('зіпсовані налаштування панелей → типові 35°/0°/80%', pg.evaluate("JSON.stringify([...document.querySelectorAll('#loc input')].map(i=>i.value).filter(Boolean))").find('35') >= 0)
    pg.wait_for_timeout(5000); g2 = os.path.join(tmp, 'good.json'); json.dump(good, open(g2, 'w'))
    pg.set_input_files('#file', g2); pg.wait_for_timeout(1500)
    ok('невірне значення не лишається у списку горизонту', pg.evaluate("document.querySelectorAll('[data-in=\"B65\"] option').length") == 11)
    ok('повідомлення не стирає таймер попереднього файлу', pg.locator('#filemsg').inner_text() != '')
    # довге слово в назві
    setv(pg, 'B5', 'Я' * 400); pg.click('[data-tab="p_res"]'); pg.wait_for_timeout(300)
    ok('назва з 400 символів без пробілів не розширює сторінку', pg.evaluate('document.documentElement.scrollWidth') <= 1400)
    setv(pg, 'B5', 'Тест')
    ok('немає помилок JS', not errs, str(errs[:3]))
    ctx.close()
    # 14 мобільний
    ctx, pg, errs = start(b, (380, 800))
    for tab in ['p_res', 'p_in', 'p_det', 'p_met']:
        pg.click(f'[data-tab="{tab}"]'); pg.wait_for_timeout(300)
        ow = pg.evaluate("document.documentElement.scrollWidth")
        ok(f'мобільний 380 px, вкладка {tab}: сторінка не з’їжджає', ow <= 392, f'scrollWidth {ow}')
    pg.click('[data-tab="p_res"]')
    ok('мобільний: графіки читабельні (гортаються, не стискаються)', pg.evaluate("document.querySelector('#c1 svg').getBoundingClientRect().width>=600"))
    ok('мобільний: без помилок JS', not errs, str(errs[:3]))
    ctx.close(); b.close()
srv.shutdown()
bad = [x for x in R if not x[1]]
for n, c, i in R: print(('OK  ' if c else 'FAIL'), n, ('– ' + i if i and not c else ''))
print('\n%d перевірок, провалів: %d' % (len(R), len(bad)))
sys.exit(1 if bad else 0)
