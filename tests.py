import unittest
import json


class UrlTest(unittest.TestCase):
    def check_keyword_presence(self, fp: str, keywords: list):
        """
        fp: File Path to the JSONL file (containing urls of the sites scraped),
        keyword: List[str] of keywords to check for presence
        """

        urls = []
        bools = []

        try:
            with open(fp, "r") as f:
                lines = f.readlines()
                for line in lines:
                    dictobj = json.loads(line)
                    urls.append(dictobj["url"])

        except FileNotFoundError:
            raise Exception(f"{fp} not found.")

        for u in urls:
            bools.append(any(k in u for k in keywords))

        ideal = [True for _ in urls]

        return self.assertEqual(bools, ideal)
