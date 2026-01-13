import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from .common import Component, EcadParser


@dataclass
class MillimeterPerPixel:
    value: float


@dataclass
class Pixel:
    value: float

    def __mul__(self, factor: float):
        return Pixel(self.value * factor)

@dataclass
class BOMItem:
    qty: int
    value: str
    footprint: str
    refdes: list[tuple[str, int]]

    def serialize(self) -> list:
        return [
            self.qty,
            self.value,
            self.footprint,
            [[*r] for r in self.refdes],
            [],
        ]


@dataclass
class BOM:
    B: list[BOMItem]
    F: list[BOMItem]
    both: list[BOMItem]

    def serialize(self) -> dict:
        return {
            "B": [r.serialize() for r in self.B],
            "F": [r.serialize() for r in self.F],
            "both": [r.serialize() for r in self.both],
            "skipped": [],
        }


class Millimeter:
    def __init__(self, value: float):
        self.value = value

    def __add__(self, other: Self):
        return Millimeter(self.value + other.value)

    def __sub__(self, other: Self):
        return Millimeter(self.value - other.value)

    def __mul__(self, factor: float):
        return Millimeter(self.value * factor)

    def __truediv__(self, ratio: MillimeterPerPixel) -> Pixel:
        return Pixel(self.value / ratio.value)


@dataclass
class SilkscreenPNG:
    prefix: str
    start: tuple[float, float] = (0, 0)

    def serialize(self, is_front: bool):
        return {
            "start": [self.start[0], self.start[1]],
            "type": "url",
            "url": self.prefix + ("-front.png" if is_front else "-back.png"),
        }

def pixel_encoder(obj) -> float:
    if isinstance(obj, Pixel):
        return obj.value

    # If the object is of an unsupported type, raise a TypeError
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


class GenericCentroidParser(EcadParser):
    """Generic centroid file parser"""

    def __init__(
        self,
        file_name: str,
        width: Millimeter,
        height: Millimeter,
        mpp: MillimeterPerPixel,
    ):
        EcadParser.__init__(self, file_name, None, None)
        self.width = width
        self.height = height
        self.mpp = mpp
        self.bbox_size = Millimeter(0.1 * 25.4) / mpp
        self.conn: sqlite3.Connection | None = None

    def parse_xy(self) -> None:
        """Parse the centroid file"""

        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.execute("""CREATE TABLE xy(refdes STRING PRIMARY KEY,
               x FLOAT, y FLOAT, angle FLOAT, side STRING)""")
        self.conn.execute("""CREATE TABLE bom(refdes STRING PRIMARY KEY,
               footprint STRING, value STRING, side STRING)""")

        self.conn.commit()

        with open(self.file_name, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip all comments
                if row[0][0] == "#":
                    continue

                # Parse cells
                refdes = row[0]
                description = row[1]
                value = row[2]
                rotation = float(row[5])
                coord_x = Millimeter(float(row[3])) / self.mpp
                y = Millimeter(float(row[4]))

                if row[6] == "top":
                    top_or_bottom = "F"
                    # Centroid file coordinates' origin is at bottom-left,
                    # but raster images have origin at top-left.
                    coord_y = (self.height - y) / self.mpp
                else:
                    top_or_bottom = "B"
                    coord_y = y / self.mpp
                    # Assuming the back-side PCB rendering is vertically flipped,
                    # so no need to flip here.

                # Append to in-memory database
                self.conn.execute(
                    "INSERT INTO bom VALUES (?,?,?,?)",
                    (refdes, description, value, top_or_bottom),
                )

                self.conn.execute(
                    "INSERT INTO xy VALUES (?,?,?,?,?)",
                    (refdes, coord_x.value, coord_y.value, rotation, top_or_bottom),
                )

            self.conn.commit()

    def get_bom(self) -> BOM:
        """Create the bill of materials."""
        assert self.conn is not None

        bom = BOM(F=[], B=[], both=[])
        for row in self.conn.execute(
            """SELECT footprint, value, side, count(*) AS qty FROM bom
                   GROUP BY side, footprint, value"""
        ):
            item = BOMItem(
                qty=row["qty"],
                value=str(row["value"]),
                footprint=str(row["footprint"]),
                refdes=[
                    (str(r["refdes"]), r["id"])
                    for r in self.conn.execute(
                        """SELECT bom.refdes, xy.rowid - 1 AS id FROM bom, xy
                     WHERE bom.refdes = xy.refdes AND
                     footprint=? AND value=?""",
                        (row["footprint"], row["value"]),
                    )
                ],
            )

            bom.both.append(item)
            if row["side"] == "F":
                bom.F.append(item)
            else:
                bom.B.append(item)

        return bom

    def get_components(self) -> list[Component]:
        """Create a list of components"""
        components = []

        assert self.conn is not None
        for row in self.conn.execute("SELECT refdes, footprint, value, side FROM bom"):
            components.append(
                Component(
                    row["refdes"],
                    str(row["value"]),
                    str(row["footprint"]),
                    str(row["side"]),
                )
            )
        return components

    def get_modules(self) -> list[dict]:
        """Create a list of modules."""
        modules = []

        assert self.conn is not None
        for row in self.conn.execute("SELECT refdes, x, y, side FROM xy"):
            modules.append(
                {
                    "center": [row["x"], row["y"]],
                    "bbox": {
                        "angle": 0,
                        "pos": [row["x"], row["y"]],
                        "relpos": [self.bbox_size * -0.5, self.bbox_size * -0.5],
                        "size": [self.bbox_size, self.bbox_size],
                    },
                    "pads": [],
                    "drawings": [],
                    "layer": row["side"],
                    "ref": str(row["refdes"]),
                }
            )

        return modules

    def get_silkscreen(self) -> SilkscreenPNG:
        """Create the link to the photorealistic rendering of PCBs in the background."""

        return SilkscreenPNG(prefix=Path(self.file_name).stem)

    def parse(self):
        """Parse the centroid file and return the pcbdata and components"""
        self.parse_xy()

        title = Path(self.file_name).stem
        date = datetime.fromtimestamp(os.path.getmtime(self.file_name)).strftime(
            "%Y-%m-%d"
        )

        silkscreen = self.get_silkscreen()

        pcbdata = {
            "edges_bbox": {
                "minx": 0,
                "miny": 0,
                "maxx": self.width / self.mpp,
                "maxy": self.height / self.mpp,
            },
            "edges": [],
            "silkscreen": {
                "F": silkscreen.serialize(True),
                "B": silkscreen.serialize(False),
            },
            "fabrication": {
                "F": [],
                "B": [],
            },
            "modules": self.get_modules(),
            "metadata": {"title": title, "company": "", "revision": "", "date": date},
            "bom": self.get_bom().serialize(),
            "font_data": {},
        }

        return pcbdata, self.get_components()
