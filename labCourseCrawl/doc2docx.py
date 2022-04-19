import os
from win32com import client as wc


pathNow = os.getcwd()
path2doc = pathNow + '\\docFiles\\'
path2docx = pathNow + '\\docxFiles\\'

# 参考 https://zhuanlan.zhihu.com/p/88303305

word = wc.Dispatch("Word.Application")
filenamelist = os.listdir(path2doc)
for i in filenamelist:
    # 找出文件中以.doc结尾并且不以~$开头的文件（~$是为了排除临时文件的）
    if i.endswith('.doc') and not i.startswith('~$'):
        print(i)
        # 打开文件
        doc = word.Documents.Open(path2doc + i)
        # 将文件另存为.docx
        doc.SaveAs(path2docx + i + 'x', 12)  # 12表示docx格式
        doc.Close()
    else:
        print('非doc文件：' + i)
word.Quit()
