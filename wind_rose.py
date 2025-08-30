#!/usr/bin/env python3
import csv
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Self

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from PIL import Image
from PIL.Image import Image as ImageType
from tqdm import tqdm

pl.Config.set_tbl_hide_dataframe_shape(True)
pl.Config.set_tbl_hide_column_data_types(True)
DEBUG: bool = False
mpl.rcParams["font.family"] = "Noto Sans JP"


class WindRose:
    summer_months: list[int] = [4, 5, 6, 7, 8, 9, 10, 11]
    winter_months: list[int] = [12, 1, 2, 3]
    wind_path: Path = Path("wind.csv")
    map_path: Path = Path("map.png")
    fig_dir_path: Path = Path("diagrams")
    directions: list[str] = [
        "北",
        "北北東",
        "北東",
        "東北東",
        "東",
        "東南東",
        "南東",
        "南南東",
        "南",
        "南南西",
        "南西",
        "西南西",
        "西",
        "西北西",
        "北西",
        "北北西",
        "静穏",
    ]
    color_palette: list[tuple[float, float, float]] = sns.hls_palette(
        13,
        l=0.5,
        s=1.0,
    )

    def __init__(self: Self, angle: int = 0) -> None:
        # create figure directory
        if not self.fig_dir_path.is_dir():
            self.fig_dir_path.mkdir(parents=True, exist_ok=True)
        # direction to index mapping
        self.direction_to_index: dict[str, int] = {
            d: i for i, d in enumerate(self.directions)
        }
        # read wind data
        if not self.wind_path.is_file():
            raise FileNotFoundError(f"'{self.wind_path}' not found.")
        self.read_wind()
        # set angle
        while angle < 0:
            angle += 360
        while angle >= 360:
            angle -= 360
        self.angle: int = angle
        # read map
        if not self.map_path.is_file():
            raise FileNotFoundError(f"'{self.map_path}' not found.")
        self.read_map()
        return

    def parse_wind_direction(self: Self, raw: str) -> int:
        raw_starts: bool = raw == "" or raw.startswith(tuple(self.directions))
        raw_ends: bool = raw == "" or raw.endswith(tuple(self.directions))
        if raw_starts ^ raw_ends:
            if raw_starts:
                while True:
                    raw = raw[:-1]
                    if raw in self.directions:
                        break
                    elif raw == "":
                        raise ValueError("Invalid direction")
            else:  # raw_ends
                while True:
                    raw = raw[1:]
                    if raw in self.directions:
                        break
                    elif raw == "":
                        raise ValueError("Invalid direction")
        return (
            self.direction_to_index["静穏"]
            if raw == ""
            else self.direction_to_index[raw]
        )

    def read_wind(self: Self) -> None:
        wind_data: list[dict[str, Any]] = []
        with open(self.wind_path, encoding="utf-8-sig") as wind_f:
            wind_reader: csv.reader = csv.reader(wind_f, delimiter=",")
            for row in wind_reader:
                try:
                    dt: datetime = datetime.strptime(
                        row[0].strip(),
                        "%Y/%m/%d %H:%M:%S",
                    )
                    dt -= timedelta(hours=1)
                    day: datetime = dt.replace(
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                    month: int = dt.month
                    row1: str = row[1].strip()
                    wind: float = 0 if row1 == "" else float(row1)
                    row3: str = row[3].strip()
                    direction_index: int = self.parse_wind_direction(raw=row3)
                except Exception as e:
                    print(row)
                    raise e
                wind_data.append(
                    {
                        "datetime": dt,
                        "day": day,
                        "month": month,
                        "wind": wind,
                        "direction_index": direction_index,
                    }
                )
        raw_df: pl.DataFrame = pl.DataFrame(wind_data)
        counts_df: pl.DataFrame = raw_df.group_by(["month"]).agg(
            nhours=pl.len(),
        )
        raw_df = raw_df.join(counts_df, on="month", how="left")
        data_df: pl.DataFrame = raw_df.group_by(
            [
                "month",
                "direction_index",
            ]
        ).agg(
            wind_percentage=pl.len() / pl.col("nhours").first() * 100.0,
            wind_mean=pl.col("wind").mean(),
            wind_max=pl.col("wind").max(),
        )
        self.data_df = data_df.fill_nan(0)
        return

    def center_crop(
        self: Self,
        orig: ImageType,
        width: int,
        height: int,
    ) -> ImageType:
        orig_width, orig_height = orig.size
        crop_left: int = (orig_width - width) // 2 if orig_width > width else 0
        crop_top: int = (
            (orig_height - height) // 2 if orig_height > height else 0
        )
        cropped: ImageType = orig.crop(
            (crop_left, crop_top, crop_left + width, crop_top + height)
        )
        cropped_width, cropped_height = cropped.size
        padding_left: int = (width - cropped_width) // 2
        padding_top: int = (height - cropped_height) // 2
        background: ImageType = Image.new(
            "RGB",
            (width, height),
            (255, 255, 255),
        )
        background.paste(cropped, (padding_left, padding_top))
        return background

    def read_map(self: Self) -> None:
        raw_map: ImageType = Image.open(self.map_path).convert("RGBA")
        raw_width, raw_height = raw_map.size
        cropped_map: ImageType = self.center_crop(
            orig=raw_map,
            width=640,
            height=640,
        ).rotate(self.angle)
        background: ImageType = Image.new(
            "RGB",
            (550, 450),
            (255, 255, 255),
        )
        background.paste(
            self.center_crop(
                orig=cropped_map,
                width=450,
                height=450,
            ),
            (0, 0),
        )
        self.map_image: ImageType = background
        return

    def create_lader_chart(
        self: Self,
        column: str,
        months: list[int],
        fname: str,
    ) -> None:
        assert column in [
            "wind_percentage",
            "wind_mean",
            "wind_max",
        ]
        valid_direction_indexes: list[int] = list(range(16))
        values_dict: dict[int, list[float]] = {}
        for month in months:
            temp_df: pl.DataFrame = (
                self.data_df.select(
                    [
                        "month",
                        "direction_index",
                        column,
                    ]
                )
                .filter(
                    pl.col("month") == month,
                    pl.col("direction_index").is_in(valid_direction_indexes),
                )
                .sort(by="direction_index")
            )
            values: list[float] = (
                temp_df.select(pl.col(column)).to_series().to_list()
            )
            values_dict[month] = values
        angle_list: list[float] = [
            (0.25 - (i / 16.0) + (self.angle / 360)) * 2.0 * np.pi
            for i in range(16)
        ]
        angle_list = [x + (2.0 * np.pi) if x < 0 else x for x in angle_list]
        angle_list = [
            x - (2.0 * np.pi) if x >= 2.0 * np.pi else x for x in angle_list
        ]
        angle_list += angle_list[:1]
        fig, ax = plt.subplots(
            nrows=1,
            ncols=1,
            figsize=(5.5, 4.5),
            dpi=100,
            layout="tight",
            subplot_kw={"projection": "polar"},
        )
        # plt.imshow(self.map_image)
        plt.xticks(angle_list[:-1], self.directions[:-1], fontsize=12)
        for month in months:
            draw_values: list[float] = values_dict[month]
            draw_values += draw_values[:1]
            ax.plot(
                angle_list,
                draw_values,
                linewidth=2,
                label=f"{month}月",
                color=self.color_palette[month - 1],
            )
        plt.legend(bbox_to_anchor=(1.1, 0.95), loc="upper left", fontsize=10)
        temp_path: Path = self.fig_dir_path / "_temp.png"
        fig.savefig(temp_path, transparent=True)
        plt.close()
        # overlay graph on map
        rose: ImageType = Image.new(
            "RGB",
            (550, 450),
            (255, 255, 255),
        )
        rose.paste(self.map_image, (0, 0))
        graph: ImageType = Image.open(temp_path).convert("RGBA")
        rose.paste(graph, (-10, 0), graph)
        rose.save(self.fig_dir_path / fname)
        temp_path.unlink(missing_ok=True)
        return

    def generate(self) -> None:
        # Placeholder for wind rose generation logic
        all_months: list[int] = list(range(1, 13))
        for name, months in tqdm(
            [
                ("year", all_months),
                ("summer", self.summer_months),
                ("winter", self.winter_months),
            ],
            desc="[Season]",
        ):
            if len(months) == 0:
                continue
            for column in tqdm(
                [
                    "wind_percentage",
                    "wind_mean",
                    "wind_max",
                ],
                desc="[Type]",
                leave=False,
            ):
                self.create_lader_chart(
                    column=column,
                    months=months,
                    fname=f"{column}_{name}.png",
                )
        return


def main() -> None:
    parser: ArgumentParser = ArgumentParser(
        description="Generate wind rose diagrams.",
    )
    parser.add_argument(
        "--angle",
        "-a",
        type=int,
        default=0,
        help="The angle to rotate wind rose diagrams (default: 0)",
    )
    args: Namespace = parser.parse_args()
    wind_rose: WindRose = WindRose(**vars(args))
    wind_rose.generate()
    return


if __name__ == "__main__":
    main()
