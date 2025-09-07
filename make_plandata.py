"""
【make_plandata.py】
    工事毎の周期データから長期修繕計画用csvデータを作成する。
    programming by N.Goto

入力する周期データ：
    - ヘッダー行 [ver, 工事種別, 工事名, 第1回目の工事年, 工事周期, 金額（消費税・経費別), 備考]
    - 2行目以降 上記のデータ

出力する長期修繕計画データ：
    - ヘッダー行なし
    - [ver, 予定年, 工事種別, 工事名, 数量(1に固定), 単位(式に固定), 予定金額, 実質金額(0に固定), 備考]
"""

import argparse
import csv
import datetime
import os
import sys
from pathlib import Path
from textwrap import dedent
from typing import List, Union

# 1つの工事項目について最大100年分(回分)
limmit_num = 100


def main():
    # 修繕計画データリスト
    # 引数のパーサーを作成（ヘルプ表示のフォーマットを指定する）
    parser = argparse.ArgumentParser(
        description="長期修繕計画データを作成するスクリプト", formatter_class=argparse.RawTextHelpFormatter
    )

    # デフォルトの計画期間は当年から35年後まで
    start_year = datetime.datetime.now().year
    last_year = start_year + 36

    # ヘルプメッセージの作成（dedentで行頭のインデントを削除する）
    help_msg = dedent("""\
            データファイル名（構造は9列のcsvファイル）
            (1) バージョン番号,
            (2) 実施年度,
            (3) 工事タイプ,
            (4) 工事名,
            (5) 数量（基本的に「1」）,
            (6) 単位（基本的に「式」）,
            (7) 予算,
            (8) 実績値（基本的に「0」）,
            (9) コメント """)

    # 引数を定義
    parser.add_argument("-f", "--csv_file_path", type=str, required=True, help=help_msg)
    parser.add_argument(
        "-s", "--start_year", type=int, default=start_year, help="計画の初年度（default：当年度）"
    )
    parser.add_argument(
        "-e", "--last_year", type=int, default=last_year, help="計画の最終年度+1（default：当年度+36年）"
    )

    # 引数の読み込み
    args = parser.parse_args()
    file_path = args.csv_file_path
    start_year = args.start_year
    last_year = args.last_year

    if last_year <= start_year:
        print("計画の最終年度か計画の初年度を見直ししてください。")
        sys.exit()
    elif last_year - start_year > limmit_num:
        print(f"計画期間は{limmit_num}年以内にしてください。")
        sys.exit()

    # (1) csvファイルの読み込み
    data_list = read_csv(file_path)

    # (2) 周期データの作成
    plan_list = make_plan(data_list, start_year, last_year)

    # (3) 工事の無い年はdummy工事を追加
    full_plan_list = fill_dummydata(plan_list, start_year, last_year)

    # (4) 作成したデータをcsvファイルとして保存
    output_file = os.path.splitext(file_path)[0] + "_out.csv"
    save_csv(output_file, full_plan_list)


# CSVファイルの読み込み
def read_csv(file_path: Union[str, Path]) -> List[List[str]] | bool:
    """
    CSV ファイルを読み込み、データをリストで返す。失敗した時にはboolean値（False）を返す。

    Parameters
    ----------
    file_path : str | Path
        読み込む CSV ファイルのパス。

    Returns
    -------
    list[list[str]] | bool
        読み込んだ行データ（ヘッダ行を除く）。
        重大なエラーがある場合は False を返す。

    エラールール
    ------------
    * ファイルが存在しない → False
    * 1列目（バージョン番号）が空欄の行を検出 → False
    * CSV フォーマットエラー → False
    """
    path = Path(file_path)

    # 1. ファイル存在確認
    if not path.is_file():
        print(f"ファイルが見つかりません: {path}", file=sys.stderr)
        return False

    # 型ヒント付きの空リストを作成
    rows: list[list[str]] = []

    try:
        # 2. BOM付きUTF‑8も考慮し、改行はcsvモジュールに任せる
        with path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            _ = next(reader, None)

            for line_no, row in enumerate(reader, start=2):
                # 3‑A. ファイル末尾の空行などはスキップ
                if not row or all(cell.strip() == "" for cell in row):
                    continue

                # 3‑B. 1列目チェック（csvデータ作成時に忘れることがあるため）
                if row[0].strip() == "":
                    print(f"{line_no} 行目のバージョン番号が空欄です: {row}", file=sys.stderr)
                    return False

                rows.append(row)

    except csv.Error as e:  # フォーマット異常
        print(f"CSV 解析中にエラー（{e}）が発生しました。", file=sys.stderr)
        return False
    except Exception as e:  # それ以外
        print(f"ファイル読み込み中に予期しないエラー: {e}", file=sys.stderr)
        return False

    return rows


def make_plan(data_list, start_year, last_year):
    """
    周期データの作成
    - 工事名毎に最大100回分の工事予定を作成.
    """
    plan_list = []
    for row in data_list:
        # 最初の工事を行う年（西暦）
        yyyy = int(row[3])
        # 1つの工事項目についてlimmit_num回繰り返す
        for i in range(1, limmit_num):
            # 予定年度が最終計画年度以上になったら、次の工事名処理を行う.
            if yyyy >= last_year:
                break
            else:
                # 工事データをplan_listに追加して、次の工事予定年（西暦）を求める
                yyyy = add_planlist(row, yyyy, start_year, plan_list)
                # 周期（row[4]）が0なら1回だけの工事なのでbreakして抜ける
                if int(row[4]) < 1:
                    break

    return plan_list


def add_planlist(row, yyyy, start_year, plan_list):
    """
    修繕計画データリストに追加する処理
    """

    # rowリストをtmplistにコピー
    tmplist = row[:]
    # 不要データを削除
    del tmplist[3:5]
    tmplist.insert(1, yyyy)  # 施工予定年
    tmplist.insert(4, 1)  # 数量は「1」に固定
    tmplist.insert(5, "式")  # 数量単位は「式」に固定
    tmplist.insert(7, 0)  # 実績費用は「0」に固定
    # 計画初年度以降のデータをplan_listに追加
    if yyyy >= start_year:
        plan_list.append(tmplist)
    yyyy += int(row[4])

    # 次の施工予定年を返す.
    return yyyy


def fill_dummydata(plan_list, start_year, last_year):
    """
    抜けている年のデータ（ダミーデータ）を追加する
    - 長期修繕計画では期間中の工事予定が無い年のデータも必要
    """

    # 工事予定年だけのリストを作成
    year_list = []
    for i in plan_list:
        year_list.append(i[1])
    # 重複年を除去
    unique_year_list = list(set(year_list))
    # 重複を除去したリストを昇順にソート
    unique_year_list.sort()

    for cnt_year in range(start_year, last_year):
        # データが存在すればスキップする
        if cnt_year in unique_year_list:
            pass
        else:
            # 不足している年のダミーデータをplan_listに追加する
            dummy_data = [5, 0, "ダミー工事", "ダミー工事", 1, "式", 0, 0, ""]
            dummy_data[1] = cnt_year
            plan_list.append(dummy_data)
        cnt_year += 1

    return plan_list


# CSVファイルにリストを書き込む
def save_csv(file_path, data_list):
    """
    リスト（リストのリスト）をCSVファイルに書き込む関数。
    """
    if not data_list:
        print("データが空のため、ファイルに書き込みません。")
        return False

    try:
        with open(file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerows(data_list)
        return True
    except Exception as e:
        print(f"ファイル書き込み中にエラーが発生しました: {e}")
        return False


if __name__ == "__main__":
    main()
