import io
import os
import sys

from .common import EcadParser, Component, BoundingBox

PY3 = sys.version_info[0] == 3

if PY3:
    string_types = str
else:
    string_types = basestring


class GenericCentroidParser(EcadParser):

    def __init__(self, file_name, config, logger, width=0., height=0., mpp=25.4/600):
        EcadParser.__init__(self, file_name, config, logger)
        self.WIDTH = width
        self.HEIGHT = height
        self.MPP = mpp
        self.BBOX_SIZE = 0.1 * 25.4 / self.MPP

    def parseXy(self):
        import sqlite3

        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row

        self.conn.execute(
            'CREATE TABLE xy(refdes STRING PRIMARY KEY, x FLOAT, y FLOAT, angle FLOAT, side STRING)'
        )
        self.conn.execute(
            'CREATE TABLE bom(refdes STRING PRIMARY KEY, footprint STRING, value STRING, side STRING)'
        )

        self.conn.commit()

        import csv

        with open(self.file_name, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip all comments
                if row[0][0] == '#':
                    continue

                # Parse cells
                refdes = row[0]
                description = row[1]
                value = row[2]
                y = (self.HEIGHT - float(row[4])) / self.MPP
                rotation = float(row[5])

                if row[6] == 'top':
                    top_or_bottom = 'F'
                    x = float(row[3]) / self.MPP
                else:
                    top_or_bottom = 'B'
                    # In iBom, the x coord is horizontally flipped
                    x = (self.WIDTH - float(row[3])) / self.MPP

                # Append to in-memory database
                self.conn.execute('INSERT INTO bom VALUES (?,?,?,?)',
                                  (refdes, description, value, top_or_bottom))

                self.conn.execute('INSERT INTO xy VALUES (?,?,?,?,?)',
                                  (refdes, x, y, rotation, top_or_bottom))

            self.conn.commit()

    def getBom(self):
        self.bom = {'B': [], 'F': [], 'both': [], 'skipped': []}

        for row in self.conn.execute(
                '''SELECT footprint, value, side, count(*) AS qty FROM bom
                   GROUP BY side, footprint, value'''):
            bom_group = [
                row['qty'],
                str(row['value']),
                str(row['footprint']),
                [[str(r['refdes']), r['id']] for r in self.conn.execute(
                    '''SELECT bom.refdes, xy.rowid - 1 AS id FROM bom, xy
                     WHERE bom.refdes = xy.refdes AND footprint=? AND value=?''',
                    (row['footprint'], row['value']))], []
            ]

            self.bom['both'].append(bom_group)
            self.bom[row['side']].append(bom_group)

    def getComponents(self):
        self.components = []

        for row in self.conn.execute(
                'SELECT refdes, footprint, value, side FROM bom'):
            self.components.append(
                Component(row['refdes'], str(row['value']), str(
                    row['footprint']), str(row['side'])))

    def getModules(self):
        self.modules = []

        for row in self.conn.execute('SELECT refdes, x, y, side FROM xy'):
            self.modules.append({
                'center': [row['x'], row['y']],
                'bbox': {
                    'angle': 0,
                    'pos': [row['x'], row['y']],
                    'relpos': [self.BBOX_SIZE * -0.5, self.BBOX_SIZE * -0.5],
                    'size': [self.BBOX_SIZE, self.BBOX_SIZE],
                },
                'pads': [],
                'drawings': [],
                'layer': row['side'],
                'ref': str(row['refdes']),
            })

    def getBackground(self):
        self.silkscreen = dict(F=[], B=[])

        basename = os.path.splitext(self.file_name)[0]

        self.silkscreen['F'].append({
            "start": [0, 0],
            "type": "url",
            "url": basename + "-front.png"
        })

        self.silkscreen['B'].append({
            "start": [0, 0],
            "type": "url",
            "url": basename + "-back.png"
        })

    def parse(self):

        self.getBackground()
        self.parseXy()
        self.getBom()
        self.getModules()

        pcbdata = {
            "edges_bbox": {
                "minx": 0,
                "miny": 0,
                "maxx": self.WIDTH / self.MPP,
                "maxy": self.HEIGHT / self.MPP
            },
            "edges": [],
            "silkscreen":
            self.silkscreen,
            "fabrication": {
                'F': [],
                'B': [],
            },
            "modules":
            self.modules,
            "metadata": {
                "title": "unamed",
                "company": "unamed",
                "revision": "v0.0",
                "date": ""
            },
            "bom":
            self.bom,
            "font_data": {}
        }

        self.getComponents()

        return pcbdata, self.components
