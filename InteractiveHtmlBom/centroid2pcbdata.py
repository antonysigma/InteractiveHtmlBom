import json
import argparse
from ecad.generic import GenericCentroidParser

parser = argparse.ArgumentParser(description='Parse centroid file')
parser.add_argument('-i','--input', metavar='board.xy', type=str,
                    help='Input centroid file')
parser.add_argument('-o','--output', metavar='pcbdata.json', type=str,
                    help='Output pcbdata file')
parser.add_argument('-W','--width', metavar='M', type=float,
                    help='Width of image, in mm')
parser.add_argument('-H','--height', metavar='N', type=float,
                    help='Height of image, in mm')
parser.add_argument('-m','--mpp', metavar='D', type=float,
                    help='micrometer per pixel of photorealistic PCB images')

args = parser.parse_args()

CONFIG = None
LOGGER = None
centroid_file = GenericCentroidParser(args.input, CONFIG, LOGGER,
    args.width, args.height, args.mpp)

pcbdata, components = centroid_file.parse()
pcbdata['ibom_version'] = 'v1.3'

with open(args.output, 'w') as f:
    json.dump(pcbdata, f, indent=2)
