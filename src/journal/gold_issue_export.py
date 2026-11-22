"""Public, journal-scoped issue metadata downloads for the Gold homepage.

No persistence, schema migration, external services, or third-party XLSX library.
Only published articles belonging to the requested issue/journal are exported.
"""
from datetime import date, datetime
from io import BytesIO
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import strip_tags
from django.views.decorators.http import require_GET

from journal.models import Issue
from submission.models import STAGE_PUBLISHED

SS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
CONTENT = 'http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('', SS)


def _clean(value):
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = strip_tags(str(value))
    # XML 1.0 legal characters only; avoids invalid XLSX or metadata.xml.
    return ''.join(c for c in text if c in '\t\n\r' or ord(c) >= 32 and ord(c) not in (0xFFFE, 0xFFFF))


def _data(request, issue_id):
    journal = getattr(request, 'journal', None)
    if journal is None:
        raise Http404('Journal not found')
    issue = get_object_or_404(Issue, pk=issue_id, journal=journal)
    articles = list(issue.articles.filter(journal=journal, stage=STAGE_PUBLISHED).order_by('pk'))
    metadata = [
        ('Journal', getattr(journal, 'name', '')),
        ('Journal Code', getattr(journal, 'code', '')),
        ('Print ISSN', getattr(journal, 'pissn', '')),
        ('Electronic ISSN', getattr(journal, 'issn', '')),
        ('Issue ID', issue.pk),
        ('Issue Title', getattr(issue, 'issue_title', '')),
        ('Volume', issue.volume),
        ('Issue Number', issue.issue),
        ('Issue Date', getattr(issue, 'date', '')),
        ('Description', getattr(issue, 'short_description', '')),
        ('Published Articles', len(articles)),
    ]
    headings = ['No.', 'Article ID', 'Title', 'Authors', 'Abstract', 'DOI',
                'DOI URL', 'Publication Date', 'Section', 'Article URL', 'Keywords']
    rows = []
    for num, article in enumerate(articles, 1):
        section = getattr(article, 'section', None)
        remote = getattr(article, 'is_remote', False)
        article_url = getattr(article, 'remote_url', '') if remote else getattr(article, 'url', '')
        if article_url and not str(article_url).startswith(('https://', 'http://')):
            article_url = request.build_absolute_uri(str(article_url))
        doi = article.get_doi() if callable(getattr(article, 'get_doi', None)) else ''
        doi_url = article.get_doi_url() if callable(getattr(article, 'get_doi_url', None)) else ''
        keyword_manager = getattr(article, 'keywords', None)
        if keyword_manager is not None and hasattr(keyword_manager, 'all'):
            keywords = ', '.join(str(getattr(keyword, 'word', keyword)) for keyword in keyword_manager.all())
        else:
            keywords = ''
        rows.append([num, article.pk, article.title, article.author_list,
                     article.abstract, doi, doi_url, article.date_published,
                     getattr(section, 'name', ''), article_url, keywords])
    return issue, metadata, headings, rows


def _xl_col(n):
    result = ''
    while n:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet(headers, rows, widths):
    ws = ET.Element(f'{{{SS}}}worksheet')
    views = ET.SubElement(ws, f'{{{SS}}}sheetViews')
    view = ET.SubElement(views, f'{{{SS}}}sheetView', workbookViewId='0')
    ET.SubElement(view, f'{{{SS}}}pane', ySplit='1', topLeftCell='A2', activePane='bottomLeft', state='frozen')
    cols = ET.SubElement(ws, f'{{{SS}}}cols')
    for index, width in enumerate(widths, 1):
        ET.SubElement(cols, f'{{{SS}}}col', min=str(index), max=str(index), width=str(width), customWidth='1')
    data = ET.SubElement(ws, f'{{{SS}}}sheetData')
    for ri, row_values in enumerate([headers, *rows], 1):
        row = ET.SubElement(data, f'{{{SS}}}row', r=str(ri))
        for ci, raw in enumerate(row_values, 1):
            address = f'{_xl_col(ci)}{ri}'
            if isinstance(raw, int) and not isinstance(raw, bool) and ri > 1:
                c = ET.SubElement(row, f'{{{SS}}}c', r=address, t='n')
                ET.SubElement(c, f'{{{SS}}}v').text = str(raw)
            else:
                c = ET.SubElement(row, f'{{{SS}}}c', r=address, t='inlineStr', s='1' if ri == 1 else '0')
                ins = ET.SubElement(c, f'{{{SS}}}is')
                ET.SubElement(ins, f'{{{SS}}}t').text = _clean(raw)
    return ET.tostring(ws, encoding='utf-8', xml_declaration=True)


def _xlsx(issue_metadata, headings, articles):
    metadata_rows = [[key, value] for key, value in issue_metadata]
    issue_sheet = _sheet(['Field', 'Value'], metadata_rows, [28, 65])
    article_sheet = _sheet(headings, articles, [8, 12, 65, 35, 100, 25, 45, 20, 25, 65, 50])
    styles = '''<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>'''
    workbook = f'''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="{SS}" xmlns:r="{REL}"><sheets>
<sheet name="Issue" sheetId="1" r:id="rId1"/>
<sheet name="Articles" sheetId="2" r:id="rId2"/>
</sheets></workbook>'''
    rels = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG}">
<Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="{REL}/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="{REL}/styles" Target="styles.xml"/>
</Relationships>'''
    root_rels = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    types = f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CONTENT}">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as z:
        for name, content in {
            '[Content_Types].xml': types,
            '_rels/.rels': root_rels,
            'xl/workbook.xml': workbook,
            'xl/_rels/workbook.xml.rels': rels,
            'xl/styles.xml': styles,
            'xl/worksheets/sheet1.xml': issue_sheet,
            'xl/worksheets/sheet2.xml': article_sheet,
        }.items():
            z.writestr(name, content)
    return output.getvalue()


def _filename(issue, extension):
    return f'issue-{issue.pk}-volume-{re.sub(r"[^A-Za-z0-9_-]", "-", str(issue.volume))}.{extension}'


@require_GET
def export_issue_xlsx(request, issue_id):
    issue, metadata, headings, rows = _data(request, issue_id)
    payload = _xlsx(metadata, headings, rows)
    response = HttpResponse(payload, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{_filename(issue, "xlsx")}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@require_GET
def export_issue_xml(request, issue_id):
    issue, metadata, headings, rows = _data(request, issue_id)
    root = ET.Element('issue_metadata', version='1')
    issue_el = ET.SubElement(root, 'issue')
    for key, value in metadata:
        element_name = re.sub(r'[^a-z0-9]+', '_', key.lower()).strip('_')
        ET.SubElement(issue_el, element_name).text = _clean(value)
    articles_el = ET.SubElement(root, 'articles')
    for record in rows:
        item = ET.SubElement(articles_el, 'article')
        for key, value in zip(headings, record):
            element_name = re.sub(r'[^a-z0-9]+', '_', key.lower()).strip('_')
            ET.SubElement(item, element_name).text = _clean(value)
    response = HttpResponse(ET.tostring(root, encoding='utf-8', xml_declaration=True), content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{_filename(issue, "xml")}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
