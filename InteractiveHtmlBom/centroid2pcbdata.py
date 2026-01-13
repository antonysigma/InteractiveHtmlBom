import argparse
import json

from ecad.generic import (
    GenericCentroidParser,
    Millimeter,
    MillimeterPerPixel,
    pixel_encoder,
)
from version import version

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse centroid file")
    parser.add_argument(
        "-i",
        "--input",
        metavar="board.xy",
        type=str,
        required=True,
        help="Input centroid file",
    )
    parser.add_argument(
        "-W",
        "--width",
        metavar="W",
        type=float,
        required=True,
        help="Width of image, in mm",
    )
    parser.add_argument(
        "-H",
        "--height",
        metavar="H",
        type=float,
        required=True,
        help="Height of image, in mm",
    )
    parser.add_argument(
        "-M",
        "--mpp",
        metavar="M",
        type=float,
        required=False,
        default=25.4 / 600,
        help="millimetrer per pixel of photorealistic PCB images",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="pcbdata.json",
        type=str,
        required=True,
        help="Output pcbdata file",
    )

    args = parser.parse_args()

    centroid_file = GenericCentroidParser(
        args.input,
        Millimeter(args.width),
        Millimeter(args.height),
        MillimeterPerPixel(args.mpp),
    )

    pcbdata, components = centroid_file.parse()
    pcbdata["ibom_version"] = version

    with open(args.output, "w") as f:
        json.dump(pcbdata, f, indent=2, default=pixel_encoder)
