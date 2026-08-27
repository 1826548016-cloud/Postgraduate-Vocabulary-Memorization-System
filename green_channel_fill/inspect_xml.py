import zipfile, re, sys

def cell_type(path):
    z = zipfile.ZipFile(path)
    data = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    # find row 2 cell B2 and F2
    for cell in ["B2", "F2", "B3", "F20"]:
        pat = re.compile(r'<c r="%s"[^>]*>.*?</c>' % cell, re.S)
        m = pat.search(data)
        print(cell, "->", m.group(0) if m else "NOT FOUND")

for p in sys.argv[1:]:
    print("FILE:", p)
    cell_type(p)
