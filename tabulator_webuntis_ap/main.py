import collections
import subprocess
import datetime
import functools
import logging
import sys
import webuntis  # type: ignore
from getpass import getpass

import click  # type: ignore
import yaml  # type: ignore

logging.basicConfig(
    filename="tabulator-webuntis.log",
    encoding="utf-8",
    level=logging.WARNING,
    filemode="w",
)


def _monday_preceding(date):
    one_day = datetime.timedelta(days=1)
    if date.weekday() == 0:
        return date
    else:
        return _monday_preceding(date - one_day)


def _coalesce_periods(list_of_periods):
    # should only coalesce adjacent periods of same class groups
    # so, first sort by class groups, then by time
    sorted_periods = sorted(
        list_of_periods,
        key=lambda p: "+".join(sorted([klasse.name for klasse in p.klassen]))
        + str(p.start),
    )

    def _smoosh(ps, p):
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
    for course_slug, course in course_data["lesmomenten"].items():
        start_semester = datetime.date(
            course["vanaf"]["jaar"], course["vanaf"]["maand"], course["vanaf"]["dag"]
        )
        end_semester = datetime.date(
            course["tot"]["jaar"], course["tot"]["maand"], course["tot"]["dag"]
        )
        all_groups = course["groepen"]
        duration = datetime.timedelta(hours=course["uren"])
        [webuntis_subject] = session.subjects().filter(id=[course["id"]])
        schedule = []
        all_schedules[course_slug] = schedule
        time_table = session.timetable(
            subject=webuntis_subject, start=start_semester, end=end_semester
        )
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
    for course_slug, schedule in all_schedules.items():
        contents = course_data["lesmomenten"][course_slug]["inhouden"]
        for counter, moment in enumerate(schedule, start=1):
            if counter <= len(contents):  # starts at 1...
                period_contents = contents[counter - 1]
            else:
                period_contents = "geen inhoud vastgelegd voor dit lesmoment"
                logging.warning(
                    f"geen inhoud vastgelegd voor {course_slug} op {moment}"
                )
            moment_slug_contents_tuples.append((moment, course_slug, period_contents))
        if counter < len(contents):
            logging.warning(f"minder momenten dan inhouden voor {course_slug}!")
    return moment_slug_contents_tuples


def enumerate_nested(lst_or_str, prefix=""):
    if isinstance(lst_or_str, str):
        return f"{prefix}{lst_or_str}"
    else:
        counter = 0
        mapped = []
        for elem in lst_or_str:
            if isinstance(elem, str):
                counter += 1
            mapped.append(enumerate_nested(elem, f"{prefix}{counter}."))
        return mapped


def flatten(lst_or_atom):
    if isinstance(lst_or_atom, list):
        flattened = []
        for elem in lst_or_atom:
            if isinstance(elem, list):
                flattened += flatten(elem)
            else:
                flattened.append(elem)
        return flattened
    else:
        return lst_or_atom


@click.command()
def tabulate():
    username = (
        subprocess.run(
            ["secret-tool", "lookup", "username", "AP"],
            capture_output=True,
            encoding="utf8",
        ).stdout
        + "@ap.be"
    )
    user_pw = subprocess.run(
        ["secret-tool", "lookup", "password", "AP"],
        capture_output=True,
        encoding="utf8",
    ).stdout
    with webuntis.Session(
        server="arche.webuntis.com",
        username=username,
        password=user_pw,
        school="AP-Hogeschool-Antwerpen",
        useragent="WebUntis Test",
    ).login() as s:
        for klasse in s.klassen():
            print(klasse.name)


if __name__ == "__main__":
    tabulate()
