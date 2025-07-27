import tempfile
import subprocess
import datetime
import functools
import webuntis  # type: ignore
import click  # type: ignore


def _coalesce_periods(list_of_periods):
    """Merge adjacent 1-hour time slots for the same group into several-hour slots.

    This is currently restricted to only work for single-class periods.
    It is possible to make this work for multi-class periods.
    However, that means we have to pay more attention to chronology.
    And in that case, we should probably split those slots into one slot per class group for the calendar."""
    # should only coalesce adjacent periods of same class groups
    # so, first sort by class groups, then by time
    sorted_periods = [
        period
        for period in sorted(
            list_of_periods,
            key=lambda p: "+".join(sorted([klasse.name for klasse in p.klassen]))
            + str(p.start),
        )
        # NOTE: this is what restricts the function to single-group
        if len(period.klassen) == 1
    ]

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
    ip = subprocess.run(
        ["secret-tool", "lookup", "IP", "Hetzner"],
        capture_output=True,
        encoding="utf8",
    ).stdout
    with webuntis.Session(
        server="arche.webuntis.com",
        username=username,
        password=user_pw,
        school="AP-Hogeschool-Antwerpen",
        useragent="WebUntis Test",
    ).login() as session:
        CLOUDSYSTEMEN = 50592
        TEST_GROUPS = ["1PRO_D1", "1PRO_D2"]
        [webuntis_subject] = session.subjects().filter(id=[CLOUDSYSTEMEN])
        time_table = session.timetable(
            subject=webuntis_subject,
            start=datetime.date(2025, 1, 1),
            end=datetime.date(2025, 7, 1),
        )
        time_table = _coalesce_periods(time_table)
        with tempfile.NamedTemporaryFile(
            # file is written on close, but removed when context handler exits
            # making it named allows copying it over
            mode="w+t",
            encoding="utf8",
            delete_on_close=False,
        ) as fp:
            for period in time_table:
                klas_names = [klas.name for klas in period.klassen]
                for klas in klas_names:
                    if klas in TEST_GROUPS:
                        fp.write(
                            f"{klas};{period.start.isoformat()};{period.end.isoformat()}\n"
                        )
            fp.close()
            _copy_result = subprocess.run(
                [
                    "scp",
                    "-i",
                    # TODO: will want to avoid referencing this in absolute terms
                    "~/.ssh/id_rsa",
                    # just to see if file shows up there
                    fp.name,
                    f"root@{ip}:/root/timetable.csv",
                ],
                capture_output=True,
                encoding="utf8",
            )


if __name__ == "__main__":
    tabulate()
