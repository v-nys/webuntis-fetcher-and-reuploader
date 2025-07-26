import collections
import datetime
import functools
import logging
import sys
import webuntis
from getpass import getpass

import click
import yaml

logging.basicConfig(filename='tabulator-webuntis.log',
                    encoding='utf-8',
                    level=logging.WARNING,
                    filemode='w')

def _monday_preceding(date):
    one_day = datetime.timedelta(days=1)
    if date.weekday() == 0:
        return date
    else:
        return _monday_preceding(date - one_day)

def _coalesce_periods(list_of_periods):
    # should only coalesce adjacent periods of same class groups
    # so, first sort by class groups, then by time
    sorted_periods = sorted(list_of_periods, key=lambda p: '+'.join(sorted([klasse.name for klasse in p.klassen])) + str(p.start))
    def _smoosh(ps,p):
        if ps == []:
            return [p]
        elif set(ps[-1].klassen) == set(p.klassen) and ps[-1].end == p.start:
            ps[-1].end = p.end
            return ps
        else:
            return ps + [p]
    coalesced = functools.reduce(_smoosh, sorted_periods, [])
    return coalesced

def _collect_schedules(session, course_data):
    """Returns a mapping from course slug to schedule. A schedule is a list of start times."""
    all_schedules = {}
    for (course_slug, course) in course_data['lesmomenten'].items():
        start_semester = datetime.date(
            course['vanaf']['jaar'],
            course['vanaf']['maand'],
            course['vanaf']['dag']
        )
        end_semester = datetime.date(
            course['tot']['jaar'],
            course['tot']['maand'],
            course['tot']['dag']
        )
        all_groups = course['groepen']
        duration = datetime.timedelta(hours=course['uren'])
        [webuntis_subject] = session.subjects().filter(id=[course['id']])
        schedule = []
        all_schedules[course_slug] = schedule
        time_table = session.timetable(subject=webuntis_subject, start=start_semester, end=end_semester)
        time_table = _coalesce_periods(time_table)
        for period in time_table:
            klas_names = [klas.name for klas in period.klassen]
            if set(all_groups) == set(klas_names):
                if period.end - period.start == duration:
                    schedule.append(period.start)
    return all_schedules

def _collect_moment_slug_contents_tuples(all_schedules, course_data):
    """Returns a list whose elements are tuples of a datetime, a course slug and the course contents taught in that course at that time.
    The course contents are a tree structure: leaves are strings, internal nodes are dicts from strings to lists."""
    moment_slug_contents_tuples = []
    for (course_slug, schedule) in all_schedules.items():
        contents = course_data['lesmomenten'][course_slug]['inhouden']
        for (counter, moment) in enumerate(schedule, start=1):
            if counter <= len(contents): # starts at 1...
                period_contents = contents[counter - 1]
            else:
                period_contents = 'geen inhoud vastgelegd voor dit lesmoment'
                logging.warning(f'geen inhoud vastgelegd voor {course_slug} op {moment}')
            moment_slug_contents_tuples.append((moment,course_slug,period_contents))
        if counter < len(contents):
            logging.warning(f'minder momenten dan inhouden voor {course_slug}!')
    return moment_slug_contents_tuples

def enumerate_nested(lst_or_str, prefix=''):
    if isinstance(lst_or_str, str):
        return f'{prefix}{lst_or_str}'
    else:
        counter = 0
        mapped = []
        for elem in lst_or_str:
            if isinstance(elem, str):
                counter += 1
            mapped.append(enumerate_nested(elem,f'{prefix}{counter}.'))
        return mapped

def flatten(lst_or_atom):
    if isinstance(lst_or_atom,list):
        flattened = []
        for elem in lst_or_atom:
            if isinstance(elem,list):
                flattened += flatten(elem)
            else:
                flattened.append(elem)
        return flattened
    else:
        return lst_or_atom

def _olify(lst):
    return f'<ol>{"".join([f"<li>{elem}</li>" if isinstance(elem,str) else _olify(elem) for elem in lst])}</ol>'

def _table_rowify(slug,counter,moment: datetime.datetime,contents):
    if isinstance(contents,list):
        contents = _olify(contents)
    style = ''
    return f'<tr {style} data-class-group="{slug}" data-date="{moment.date()}"><td>{slug}</td><td style="text-align: center">{counter}</td><td>{moment}</td><td>{contents}</td></tr>'



@click.command()
@click.argument('yamlfile')
@click.option('--chronologically/--by-grouping', default=True, help='Whether to show periods chronologically or by grouping.')
@click.option('--format', type=click.Choice(['html','csv'], case_sensitive=False), default='html')
def tabulate(yamlfile, chronologically, format):
    print('Wat is je gebruikersnaam voor WebUntis? Deze heeft de vorm p123456@ap.be', file=sys.stderr)
    username = input()
    user_pw = getpass('Wat is je wachtwoord? Dit is nodig om in te loggen op WebUntis. Het wordt niet getoond of opgeslagen.\n')
    with open(yamlfile) as fh:
        course_data = yaml.load(fh.read(), Loader=yaml.FullLoader)
    with webuntis.Session(
        server='arche.webuntis.com',
        username=username,
        password=user_pw,
        school='AP-Hogeschool-Antwerpen',
        useragent='WebUntis Test') as s:
        s.login()
        all_schedules = _collect_schedules(s, course_data)
        moment_slug_contents_tuples = _collect_moment_slug_contents_tuples(all_schedules, course_data)
        if chronologically:
            moment_slug_contents_tuples = sorted(moment_slug_contents_tuples)
        if format == 'html':
            slug_counters: collections.defaultdict = collections.defaultdict(lambda: 0)
            table_rows: str = ''
            for (moment,slug,contents) in moment_slug_contents_tuples:
                slug_counters[slug] += 1
                table_rows += _table_rowify(slug,slug_counters[slug],moment,contents)
            form: str = f"""<form><label for="datepicker">Toon vanaf:</label>
            <input type="date" id="datepicker">
            <fieldset>
            <legend>Toon voor groepen:</legend>
            {"".join([f"<label for='checkbox-{slug}'>{slug}</label><input id='checkbox-{slug}' type='checkbox' value={slug} checked>" for slug in slug_counters.keys()])}
            </fieldset>
            </form>"""
            print('<!DOCTYPE html><head><style>.out-of-range-date { display: none; } .hidden-group { display: none; } [type="checkbox"] { margin-right: 2em; }</style>'
                  '</head><body><table><thead>'
                  '<tr><th>Lessenreeks</th><th>Nummer lesmoment</th>'
                  '<th>Starttijdstip</th><th>Inhoud</th></tr></thead>'
                  f'<tbody style="vertical-align: baseline">{form}{table_rows}'
                  """</tbody></table><script>
            const datePicker = document.querySelector('#datepicker');
            const rows = document.querySelectorAll('tr');
            const OUT_OF_RANGE_DATE_CLASS_NAME = 'out-of-range-date';
            const HIDDEN_GROUP_CLASS_NAME = 'hidden-group';
            datePicker.addEventListener('change', (event) => {
                const startDate = event.target.value;
                rows.forEach((row) => {
                    if (row.getAttribute('data-date') < startDate) {
                        row.classList.add(OUT_OF_RANGE_DATE_CLASS_NAME);
                    }
                    else {
                        row.classList.remove(OUT_OF_RANGE_DATE_CLASS_NAME);
                    }
                });
            })
            const checkboxes = document.querySelectorAll('input[type="checkbox"]');
            // dit klopt niet, andere event dan change?
            checkboxes.forEach((element) => element.addEventListener('change', (event) => {
                rows.forEach((row) => {
                    if (row.getAttribute('data-class-group') === event.target.value) {
                        if (row.classList.contains(HIDDEN_GROUP_CLASS_NAME)) {
                            row.classList.remove(HIDDEN_GROUP_CLASS_NAME);
                        }
                        else {
                            row.classList.add(HIDDEN_GROUP_CLASS_NAME);
                        }
                    }
                })
            }));
        </script></body>""")
        elif format == 'csv':
            print("lessenreeks;lesmoment;datum;inhoud")
            slug_counters = collections.defaultdict(lambda: 0)
            for (moment,slug,contents) in moment_slug_contents_tuples:
                slug_counters[slug] += 1
                flattened = flatten(enumerate_nested(contents))
                print(f"{slug};{slug_counters[slug]};{moment};{' '.join(flattened) if isinstance(flattened,list) else flattened}")
        else: raise NotImplementedError("Unsupported output format.")

if __name__ == '__main__':
    tabulate()
