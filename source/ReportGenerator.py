from DrissionPage import SessionPage
from datetime import date as _date
import demoji
import codecs
import sys
import json
import os
import re
import shutil
import hashlib

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    log=""

    USEREMAIL=sys.argv[1]
    PASSWORD=sys.argv[2]
    run_id=int(sys.argv[3])
    flag=sys.argv[4]

    # USEREMAIL= 'adam.su@synaptics.com'
    # PASSWORD= 'Loveblue21716'
    # run_id=int(372552)
    # flag='i'

    print('帳號:'+USEREMAIL)
    print('密碼:********')
    print('run_id:'+str(run_id))
    if flag=='i':
        report_type='internal'
    elif flag=='e':
        report_type='external'

    print(report_type)

    # 取得目前工作目錄的絕對路徑
    base_path = os.getcwd()
    # 使用 os.path.join 組合路徑
    imgdirpath = os.path.join(base_path, str(run_id), report_type, 'imgs')
    
    # 設定模板資料夾路徑
    template_src_dir = os.path.join(base_path, 'templates')

    login_data = {'name': USEREMAIL, 'password': PASSWORD}

    # 強制建立所有層級的資料夾
    os.makedirs(imgdirpath, exist_ok=True)
    
    try:
        dirimg_result = [f for f in os.listdir(imgdirpath) if os.path.isfile(os.path.join(imgdirpath, f))]
    except Exception:
        dirimg_result = []

    # --- 讀取分類設定 ---
    category_map = {}
    category_config = {}

    sections_file = os.path.join(template_src_dir, 'TestCaseList_BySections.txt')

    # 載入自訂父分類設定
    parent_sections_file = os.path.join(template_src_dir, 'ParentSections.json')
    parent_sections_list = None
    if os.path.exists(parent_sections_file):
        try:
            with open(parent_sections_file, 'r', encoding='utf-8') as f:
                parent_sections_list = json.load(f)
            print(f"ParentSections.json loaded: {len(parent_sections_list)} parent sections.")
        except Exception as e:
            print(f"Error loading ParentSections.json: {e}")

    if os.path.exists(sections_file):
        try:
            def extract_section_map(sections, ordered_names, parent_sections_list=None, current_parent=None):
                result = {}
                for section in sections:
                    sname = section.get('SectionName', 'Others')
                    cases = section.get('mCases', [])
                    subsections = section.get('mSections', [])

                    if parent_sections_list is not None:
                        if sname in parent_sections_list:
                            effective_parent = sname
                        else:
                            effective_parent = current_parent
                    else:
                        effective_parent = sname

                    if cases:
                        label = effective_parent if effective_parent else 'Others'
                        if label not in ordered_names:
                            ordered_names.append(label)
                        for case in cases:
                            try:
                                result[int(case['ID'])] = label
                            except Exception:
                                pass
                    if subsections:
                        result.update(extract_section_map(subsections, ordered_names, parent_sections_list, effective_parent))
                return result

            for enc in ['utf-8-sig', 'cp1252', 'latin-1']:
                try:
                    with open(sections_file, 'r', encoding=enc) as f:
                        sections_data = json.load(f)
                    break
                except (UnicodeDecodeError, ValueError):
                    continue

            ordered_names = []
            category_map = extract_section_map(sections_data, ordered_names, parent_sections_list)
            ordered_by_config = parent_sections_list if parent_sections_list else ordered_names
            category_config = {name: [] for name in ordered_by_config if name in ordered_names}
            for name in ordered_names:
                if name not in category_config:
                    category_config[name] = []
            for cid, sname in category_map.items():
                category_config[sname].append(cid)
            print(f"TestCaseList_BySections.txt loaded: {len(ordered_names)} sections, {len(category_map)} cases.")
        except Exception as e:
            print(f"Error loading TestCaseList_BySections.txt: {e}")
            category_map = {}
            category_config = {}
    # ---------------------------------------------------

    # 1. 狀態 ID 對應顯示名稱
    status_info = {
        1: 'Passed',
        5: 'Failed',
        3: 'Untested',
        4: 'Retest',
        2: 'Blocked',
        6: 'Aborted',
        7: 'Partial_Pass',
        8: 'Partial_Fail',
        9: 'Conditional_Pass',
        10: 'Not_Required',
        11: 'NOT_Run',
        12: 'Unknown'
    }

    # 2. 表格背景顏色
    status_bg_colors = {
        'Passed': '#d4edda',           # 綠底
        'Failed': '#f8d7da',           # 紅底
        'Untested': '#fff3cd',         # 黃底
        'Retest': '#ffeeba',           # 黃底
        'Blocked': '#e2e3e5',          # 灰底
        'Aborted': '#f5c6cb',          # 深粉紅底
        'Partial_Pass': '#c3e6cb',     # 淺綠灰
        'Partial_Fail': '#f1b0b7',     # 淺紅灰
        'Conditional_Pass': '#d1e7dd', # 藍綠色
        'Not_Required': '#f8f9fa',     # 極淺灰
        'NOT_Run': '#d6d8db',          # 銀灰色
        'Unknown': '#ffffff'           # 白底
    }

    # 3. Summary 統計區文字顏色
    status_color = {
        'Passed': 'green',
        'Failed': 'red',
        'Untested': 'orange',
        'Retest': 'orange',
        'Blocked': 'red',
        'Aborted': 'red',
        'Partial_Pass': 'brown',
        'Partial_Fail': 'brown',
        'Conditional_Pass': 'green',
        'Not_Required': 'gray',
        'NOT_Run': 'black',
        'Unknown': 'black'
    }

    # 4. 初始化計數器
    status_amount = {name: 0 for name in status_info.values()}

    img_re=r'([!][[][]][^)]+[)])'
    img_inline_re=r"src=['\"]index\.php\?/attachments/get/([^'\"]+)['\"]"

    LOGIN_URL = 'https://synasdd.testrail.net/index.php?/auth/login/'

    flag_info={'e':['true','True',True]}

    img_num=0

    def download_img(name,filename):
        try:
            dirimg_result=[f for f in os.listdir(imgdirpath) if os.path.isfile(os.path.join(imgdirpath,f))]
        except:
            dirimg_result=[]
        special_flag=0
        img_flag=0
        name=str(name)
        if re.findall('index.php\?/attachments/get/',name):
            special_flag=1
            name="".join("".join(name.split('![](index.php?/attachments/get/')).split(')'))
        if filename=="":
            filename=name
        for img_result in dirimg_result:
            if img_result.split(".")[0]==filename:
                img_flag=1
        if filename=="":
            filename=name
        if img_flag==0 and special_flag==1:
            page.download('https://synasdd.testrail.net/index.php?/attachments/get/'+name+'/',imgdirpath,filename)
        if img_flag==0 and special_flag==0:
            page.download('https://synasdd.testrail.net/index.php?/api/v2/get_attachment/'+name+'/',imgdirpath,filename)


    def listen_json(function,offset):
        data_url='https://synasdd.testrail.net/index.php?/api/v2/'+function+'/'+str(run_id)
        if offset:
            data_url=data_url+'/3&offset='+str(offset)
        result=page.get(data_url)
        if result:
            print('資料抓取成功')
        else:
            print(page.json)
        data_json=page.json
        return data_json

    page = SessionPage(timeout=10)

    result=page.post('https://synasdd.testrail.net/index.php?/auth/login/', data=login_data)

    def get_json(get_tests_page,get_results_for_run_page,offset,get_tests_flag,get_results_for_run_flag):
        get_tests=r'./'+str(run_id)+"/"+report_type+'/get_tests'+str(get_tests_page)+'.json'
        get_results_for_run=r'./'+str(run_id)+"/"+report_type+'/get_results_for_run'+str(get_results_for_run_page)+'.json'
        if get_tests_flag!=0:
            get_tests_json=listen_json('get_tests',offset)
            f = open(get_tests, 'w',encoding="utf8")
            json.dump(get_tests_json,f,ensure_ascii=False)
            f.close()
        if get_results_for_run_flag!=0:
            get_results_for_run_json=listen_json('get_results_for_run',offset)
            f = open(get_results_for_run, 'w',encoding="utf8")
            json.dump(get_results_for_run_json,f,ensure_ascii=False)
            f.close()

        with open(get_tests,encoding='utf8') as f:
            data=json.load(f)
            if 'size' not in data or 'limit' not in data:
                raise Exception(f"Unexpected API response for get_tests: {data}")
            offset=offset+data['size']
            if data['limit']==data['size']:
                get_tests_page=get_tests_page+1
            else:
                get_tests_flag=0

        with open(get_results_for_run,encoding='utf8') as f:
            data=json.load(f)
            if 'size' not in data or 'limit' not in data:
                raise Exception(f"Unexpected API response for get_results_for_run: {data}")
            if data['limit']==data['size']:
                get_results_for_run_page=get_results_for_run_page+1
            else:
                get_results_for_run_flag=0
        global page_data
        page_data=[get_tests_page,get_results_for_run_page]
        if get_tests_flag or get_results_for_run_flag:
            get_json(get_tests_page,get_results_for_run_page,offset,get_tests_flag,get_results_for_run_flag)

    get_json(1,1,0,1,1)
    get_tests_page=page_data[0]
    get_results_for_run_page=page_data[1]

    def remove_unicode(text):
        if type(text)==str:
            text=re.sub(r'\r\n','<br>',text)
            text=re.sub(r'<<','《',text)
            text=re.sub(r'>>','》',text)
            return text.encode('ascii','ignore').decode('ascii')
        return text

    test_id={}
    test_id_img={}
    test_id_note={}
    test_id_to_case_id={} # 新增：用來存儲 test_id 對應的 case_id
    run_id_img=[]
    data={}
    replace_dict={r'\r\n':r'\n'}
    _run_api = listen_json("get_run", None)
    run_description_raw = (_run_api.get("description") or "")
    if flag=='i':
        test_id_content = run_description_raw if run_description_raw else "None"

        if re.findall(img_re,test_id_content):
            img_comment=re.findall(img_re,test_id_content)
            for one_img in img_comment:
                download_img_id="".join("".join(one_img.split('![](index.php?/attachments/get/')).split(')'))
                img_num=img_num+1
                filename=download_img_id+"_"+str(img_num)
                download_img(download_img_id,filename)
                run_id_img.append(filename)
                test_id_content="".join(test_id_content.split(one_img))
        for key,item in replace_dict.items():
            test_id_content=test_id_content.replace(key,item)
        test_id_split=test_id_content.split('\n')
                

    for page_num in range(1,int(get_tests_page)+1):
        get_tests=r'./'+str(run_id)+"/"+report_type+'/get_tests'+str(page_num)+'.json'
        with open(get_tests,encoding='utf8') as f:
            load_file=json.load(f)
            if page_num==1:
                data['tests']=load_file['tests']
            else:
                try: 
                    data['tests']=data['tests']+load_file['tests']
                except:
                    pass
    pass_id=[]

    for index in range(len(data['tests'])):
        test_id_img_criteria=[]
        current_case_id = None # 初始化 case_id
        
        for key,item in data['tests'][index].items():
            item=remove_unicode(item)
            
            # [新增] 抓取 case_id
            if key == 'case_id':
                current_case_id = item
            
            if key=='status_id' and item:
                status_id=item
            elif key=='id':
                id=item
            elif key=='title':
                test_item=item
            elif key=='custom_expected':
                if item:
                    if re.findall(img_re,item):
                        img_criteria=re.findall(img_re,item)
                        for one_img in img_criteria:
                            download_img_id="".join("".join(one_img.split('![](index.php?/attachments/get/')).split(')'))
                            if flag=='i':
                                img_num=img_num+1
                                download_img(one_img,download_img_id+"_"+str(img_num))
                                test_id_img_criteria.append(download_img_id+"_"+str(img_num))
                            item="".join(item.split(one_img))
                    for att_id in re.findall(img_inline_re,item):
                        img_num=img_num+1
                        filename="criteria_inline_"+str(img_num)
                        clean_att_id=att_id.split('#')[0]
                        page.download('https://synasdd.testrail.net/index.php?/attachments/get/'+clean_att_id+'/',imgdirpath,filename)
                        try:
                            downloaded=[f for f in os.listdir(imgdirpath) if os.path.splitext(f)[0]==filename]
                            if downloaded:
                                item=re.sub(r"src=['\"]index\.php\?/attachments/get/"+re.escape(att_id)+r"['\"]",f'src="imgs/{downloaded[0]}"',item)
                        except:
                            pass
                    criteria=item
                else:
                    criteria=''
            elif key=='custom_external_test':  
                custom_external_test=item
            else:
                pass
        
        if flag=='i' or custom_external_test in flag_info[flag]:
            if status_id in status_info.keys():
                status=status_info[status_id]
            else:
                status=status_info[12]
            status_amount[status]=status_amount[status]+1
            test_id[id]=[test_item,criteria,status,test_id_img_criteria]
            
            # [新增] 儲存該 test_id 對應的 case_id
            if current_case_id is not None:
                test_id_to_case_id[id] = current_case_id
                
        else:
            pass_id.append(id)

    for page_num in range(1,int(get_results_for_run_page)+1):
        get_results_for_run=r'./'+str(run_id)+"/"+report_type+'/get_results_for_run'+str(page_num)+'.json'
        with open(get_results_for_run,encoding='utf8') as f:
            load_file=json.load(f)
            if page_num==1:
                data['results']=load_file['results']
            else:
                try:
                    data['results']=data['results']+load_file['results']
                except:
                    pass

    test_output={}


    for index in range(len(data['results'])):
        for key,item in data['results'][index].items():
            if key=='test_id':
                id=item
                if id in pass_id:
                    break
                if id in test_id_img.keys() or id in test_id_note.keys():
                    test_output[id].append(data['results'][index])
                    break
                else:
                    test_output[id]=[data['results'][index]]
            elif key=='comment':
                test_id_img[id]=[]
                if item==None:
                    note='N/A'
                else:
                    if re.findall(img_re,item):
                        img_comment=re.findall(img_re,item)
                        test_id_img[id]=[]
                        for one_img in img_comment:
                            download_img_id="".join("".join(one_img.split('![](index.php?/attachments/get/')).split(')'))
                            test_id_img[id]=test_id_img[id]+[download_img_id]
                            item="".join(item.split(one_img))
                        note=item
                    else:
                        test_id_img[id]=[]
                        note=item
                    for att_id in re.findall(img_inline_re,note):
                        clean_att_id=att_id.split('#')[0]
                        if clean_att_id not in test_id_img[id]:
                            test_id_img[id]=test_id_img[id]+[clean_att_id]
                    note=re.sub(r'<img[^>]+src=[\'"]index\.php\?/attachments/get/[^\'">]+[\'"][^>]*/?>','',note)
                    note=re.sub(r'background-color\s*:\s*[^;"\'>]+;?\s*','',note)
                test_id_note[id]=note
            elif key=='attachment_ids':
                for one_img in item:
                    if one_img not in test_id_img[id]:
                        test_id_img[id]=test_id_img[id]+[one_img]
            else:
                pass

    for key,item in test_id_note.items():
        try:
            test_id[key]=test_id[key]+[item]
        except:
            pass

    for key,item in test_id_img.items():
        img_arr=[]
        for img_item in item:
            download_img_id=img_item
            name=""
            filename=key
            filetype=""
            if item==' ':
                pass
            else:
                result=page.get('https://synasdd.testrail.net/index.php?/api/v2/get_attachments_for_test/'+str(key))
                print(key)
                if result:
                    data_json=page.json
                    for pic_data in  data_json:
                        if pic_data["cassandra_file_id"]==download_img_id or str(pic_data["id"]) == str(download_img_id):
                            name=pic_data["name"]
                            break
                    print(name)
                    if name=="":
                        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', str(download_img_id)):
                            img_num=img_num+1
                            inline_filename="inline_"+str(img_num)
                            page.download('https://synasdd.testrail.net/index.php?/attachments/get/'+str(download_img_id)+'/',imgdirpath,inline_filename)
                            try:
                                downloaded=[f for f in os.listdir(imgdirpath) if os.path.splitext(f)[0]==inline_filename]
                                if downloaded:
                                    ext=os.path.splitext(downloaded[0])[1].lower().strip('.')
                                    if ext in ['png','jpg','jpeg']:
                                        img_arr.append(downloaded[0])
                            except:
                                pass
                        else:
                            log=log+"test id: "+str(key)+" 附件找不到對應名稱 跳過下載\n"
                    else:
                        name_split=name.split(".")
                        filetype=name_split[-1]
                        name_split.remove(name_split[-1])
                        if len(name_split)>1:
                            filename=".".join(name_split)
                        elif len(name_split)==1:
                            filename=name_split[0]
                else:
                    log=log+"test id: "+str(key)+" 檔名抓取失敗 跳過下載\n"

                if (filetype=="png" or filetype=="jpg"):
                    img_num=img_num+1
                    filename=filename+"_"+str(img_num)
                    download_img(img_item,filename)
                    img_arr.append(filename+"."+filetype)
                elif filetype!="":
                    print("檔案非圖片將跳過下載")
                    log=log+"id:"+str(key)+" 檔案:"+name+" 非圖片將跳過下載\n"
                    name=""
        def _base_name(f):
            return re.sub(r'_\d+$', '', os.path.splitext(f)[0])
        seen_hashes = {}  # hash -> first filename with that hash
        deduped_arr = []
        for img_file in img_arr:
            full_path = os.path.join(imgdirpath, img_file)
            try:
                with open(full_path, 'rb') as f:
                    h = hashlib.md5(f.read()).hexdigest()
                if h not in seen_hashes:
                    seen_hashes[h] = img_file
                    deduped_arr.append(img_file)
                else:
                    existing = seen_hashes[h]
                    is_new_inline = img_file.startswith('inline_')
                    is_existing_inline = existing.startswith('inline_')
                    if is_existing_inline and not is_new_inline:
                        # 用有意義的附件檔名取代 inline_
                        idx = deduped_arr.index(existing)
                        deduped_arr[idx] = img_file
                        seen_hashes[h] = img_file
                    elif not is_new_inline and not is_existing_inline:
                        # 同 hash 但 basename 不同 → 不同截圖（如 Jitter 不同位置）→ 保留
                        if _base_name(img_file) != _base_name(existing):
                            deduped_arr.append(img_file)
                        # 同 basename → 同一附件重複下載 → 跳過
            except:
                deduped_arr.append(img_file)
        img_arr = deduped_arr
        try:
            test_id[key]=test_id[key]+[img_arr]
        except Exception as e:
            pass

    test_number=0
    for key,item in status_amount.items():
        test_number=test_number+item

    page.close()

    # --- HTML 生成開始 ---
    html='<html><head><link rel="stylesheet" href="Report.css"><script src="Report.js"></script><meta charset="utf-8"></head>'
    html=html+'<div class="all_container">'
    html=html+"<font size='5'><b>Summary</b></font><br><font>"+str(test_number)+" tests.</font><br><font>(Un)check the boxes to filter the results.</font><br>"
    html=html+'<div class="title">'
    for key,item in status_info.items():
        if item=='Passed':
            html=html+'<input type="checkbox" id='+"'"+item+"'"+' onchange="check_status('+"'"+item+"'"')" checked><label for="'+item+'" style="color:'+status_color[item]+'">'+str(status_amount[item])+item+',</label>'
        else:
            html=html+'<input type="checkbox" id='+"'"+item+"'"+' onchange="check_status('+"'"+item+"'"')"><label for="'+item+'" style="color:'+status_color[item]+'">'+str(status_amount[item])+item+',</label>'
    html=html+'<br></div>'
    if flag=='i':
        html=html+'<div class="scroll">'
        if test_id_content!="None":
            for content in test_id_split:
                html=html+content+'<br>'
        else:
            html=html+test_id_content+'<br>'
        dirimg_result=[f for f in os.listdir(imgdirpath) if os.path.isfile(os.path.join(imgdirpath,f))]
        try:
            for img_id in run_id_img:
                for img_result in dirimg_result:
                    if img_result.split(".")[0]==img_id and not re.findall('.zip',img_result):
                        img=img_result
                        html=html+f'<a href="imgs/{img}" target="_blank"><img src="imgs/{img}" alt="{img_id}.png"></a><br>'
        except:
            pass
        html=html+'</div>'

    html=html+'<div class="line"></div>'

    # --- [核心修改] HTML 分頁生成邏輯 ---

    # 1. 準備容器
    sheet_content = {}
    
    # 2. 先建立預設的 Sheets (從 config 讀取順序)
    if category_config:
        for sheet in category_config.keys():
            sheet_content[sheet] = ""
    sheet_content["Others"] = "" # 確保 Others 存在

    dirimg_result=[f for f in os.listdir(imgdirpath) if os.path.isfile(os.path.join(imgdirpath,f))]
    
    # 3. 遍歷資料，依據 case_id 分配到對應的 Sheet
    for key, item in test_id.items():
        # 從 test_id_to_case_id 查找該 test 的 case_id
        current_case_id = test_id_to_case_id.get(key)
        
        # 決定要放在哪個 sheet
        current_sheet = category_map.get(current_case_id, "Others")
        
        status_text = item[2]
        bg_color = status_bg_colors.get(status_text, '#ffffff')
        bg_style = f'background-color: {bg_color};'

        # 開始組裝該 Row 的 HTML
        row_html = f'<tr name="{status_text}">'
        
        # Test Item
        row_html += '<td style="width:450px;">'
        if flag == 'i':
            row_html += f'<a href="https://synasdd.testrail.net/index.php?/tests/view/{key}">{item[0]}</a>'
        else:
            row_html += item[0]
        row_html += '</td>'

        # Criteria
        criteria_html = re.sub(r'<img([^>]*?)src="(imgs/[^"]+)"([^>]*?)>',r'<a href="\2" target="_blank"><img\1src="\2"\3></a>',item[1])
        row_html += f'<td style="width:300px;">{criteria_html}<br>'
        if flag == 'i':
            try:
                for img_id in item[3]:
                    for img_result in dirimg_result:
                        if img_result.split(".")[0] == img_id and not re.findall('.zip', img_result):
                            row_html += f'<a href="imgs/{img_result}" target="_blank"><img src="imgs/{img_result}" alt="{img_id}.png"></a><br>'
            except: pass
        row_html += '</td>'

        # Result
        row_html += f'<td style="width:150px; {bg_style}">{status_text}</td>'

        # Note
        row_html += f'<td style="width:600px; {bg_style} word-break: break-word; overflow-wrap: break-word;">'
        try:
            row_html += str(item[4]).replace('\r\n', '<br>').replace('\n', '<br>') + '<br>'
        except: pass
        try:
            for img_id in item[5]:
                for img_result in dirimg_result:
                    if img_result == img_id and not re.findall('.zip', img_result):
                        row_html += f'<a href="imgs/{img_result}" target="_blank"><img src="imgs/{img_result}" alt="{img_id}.png"></a><br>'
        except: pass
        row_html += '</td></tr>'

        # 將 Row 加到對應的分頁字串中
        if current_sheet not in sheet_content:
            sheet_content[current_sheet] = "" # 防呆，如果 map 有但 config key 遺失
        sheet_content[current_sheet] += row_html

    # 4. 產生 Tab 按鈕 HTML
    # 決定 Tab 顯示順序：先顯示 Category.json 裡的，最後顯示 Others
    sheet_order = list(category_config.keys())
    if "Others" not in sheet_order:
        sheet_order.append("Others")

    # 合併所有 sheet 內容為 All tab
    all_content = ''.join(sheet_content.get(s, '') for s in sheet_order)

    html += '<div class="tab">'
    # All tab 永遠在最前面且預設 active
    html += '<button class="tablinks active" onclick="openSheet(event, \'All\')">All</button>'
    for sheet_name in sheet_order:
        content = sheet_content.get(sheet_name, "")
        if len(content) > 0:
            html += f'<button class="tablinks" onclick="openSheet(event, \'{sheet_name}\')">{sheet_name}</button>'
    html += '</div>'

    # 5. 產生各分頁的 Table 內容 HTML
    # All tab 預設顯示
    html += '<div id="All" class="tabcontent" style="display: block;">'
    html += '<table><tr><th>Test Item</th><th>Criteria</th><th>Result</th><th>Note</th></tr>'
    html += all_content
    html += '</table></div>'
    for sheet_name in sheet_order:
        content = sheet_content.get(sheet_name, "")
        if len(content) > 0:
            html += f'<div id="{sheet_name}" class="tabcontent" style="display: none;">'
            html += '<table><tr><th>Test Item</th><th>Criteria</th><th>Result</th><th>Note</th></tr>'
            html += content
            html += '</table></div>'

    html += '</div></html>'

    # 寫入 HTML 檔案
    f = open(str(run_id)+"/"+report_type+"/"+str(run_id)+"_"+report_type+"_Report.html",'w', encoding='utf-8') 
    f.write(html)
    f.close()

    # 複製 Template 檔案 (從 templates 資料夾)
    report_dst_dir = str(run_id) + "/" + report_type
    template_files = ['Report.js', 'Report.css']

    for file_name in template_files:
        src_file = os.path.join(template_src_dir, file_name)
        dst_file = os.path.join(report_dst_dir, file_name)
        
        try:
            if os.path.exists(src_file):
                shutil.copy(src_file, dst_file)
                print(f"Copied template: {file_name}")
            else:
                error_msg = f"Error: Template file not found: {src_file}\n"
                print(error_msg)
                log = log + error_msg
        except Exception as copy_err:
            log = log + f"Error copying {file_name}: {str(copy_err)}\n"

    # ─── 【新增】data.json 更新 + 複製報告到共用資料夾 ──────────────────
    config_path = os.path.join(base_path, 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding='utf8') as f:
                config = json.load(f)

            shared_folder    = config.get('shared_folder', {})
            tracked_case_ids = config.get('tracked_case_ids', [])
            cfg_metrics      = config.get('tracked_metrics', [])

            def _extract_value_unit(html, unit_hint=''):
                text = ' '.join(re.sub(r'<[^>]+>', '', str(html)).split())
                if unit_hint:
                    m = re.search(r'(\d+\.?\d*)\s*' + re.escape(unit_hint), text, re.IGNORECASE)
                    if m:
                        return float(m.group(1)), unit_hint
                m = re.search(r'(\d+\.?\d*)\s*([a-zA-Z%]+)', text)
                if m:
                    return float(m.group(1)), m.group(2)
                return None, ''

            def _parse_run_desc(desc):
                info = {}
                if not desc:
                    return info
                text = re.sub(r'<[^>]+>', '', desc)
                m = re.search(r'(HQA-\d+)', text)
                if m: info['jira'] = m.group(1)
                m = re.search(r'(TM-[A-Z0-9-]+)', text)
                if m: info['tm_number'] = m.group(1)
                m = re.search(r'(PR\d+)', text)
                if m: info['pr_number'] = m.group(1)
                m = re.search(r'\((v[\d.]+)\)', text)
                if m: info['fw_version'] = m.group(1)
                m = re.search(r'\(([A-Z]+\d+)_([^_]+)_([^\s(]+)', text)
                if m:
                    info['asic']     = m.group(1)
                    info['protocol'] = m.group(2)
                    info['model']    = m.group(3)
                return info

            meta = _parse_run_desc(run_description_raw)

            # 抽取追蹤測項結果
            tracked_results = []
            for tid, cid in test_id_to_case_id.items():
                if cid in tracked_case_ids and tid in test_id:
                    t          = test_id[tid]
                    title      = t[0] if len(t) > 0 else ''
                    status_str = t[2] if len(t) > 2 else ''
                    note_html  = t[4] if len(t) > 4 else ''
                    raw_text   = ' '.join(re.sub(r'<[^>]+>', '', str(note_html)).split())
                    metric_def = next((md for md in cfg_metrics if md.get('case_id') == cid), {})
                    unit_hint  = metric_def.get('unit', '')
                    value, unit = _extract_value_unit(note_html, unit_hint)
                    tracked_results.append({
                        'case_id':     cid,
                        'title':       title,
                        'status':      status_str.lower(),
                        'value':       value,
                        'unit':        unit,
                        'raw_comment': raw_text
                    })

            # 測試統計
            new_run = {
                'run_id':      str(run_id),
                'fw_version':  meta.get('fw_version', ''),
                'pr_number':   meta.get('pr_number', ''),
                'tm_number':   meta.get('tm_number', ''),
                'jira':        meta.get('jira', ''),
                'asic':        meta.get('asic', ''),
                'protocol':    meta.get('protocol', ''),
                'model':       meta.get('model', ''),
                'date':        str(_date.today()),
                'tester':      '',
                'total_tests': sum(status_amount.values()),
                'passed':      status_amount.get('Passed', 0),
                'failed':      status_amount.get('Failed', 0),
                'blocked':     status_amount.get('Blocked', 0),
                'results':     tracked_results
            }

            # 寫入 data.json
            dashboard_dir = shared_folder.get('dashboard', '')
            if dashboard_dir:
                os.makedirs(dashboard_dir, exist_ok=True)
                data_json_path = os.path.join(dashboard_dir, 'data.json')
                if os.path.exists(data_json_path):
                    with open(data_json_path, encoding='utf8') as f:
                        data_json = json.load(f)
                else:
                    data_json = {
                        '_schema_version': '1.0',
                        'project':         {},
                        'tracked_metrics': [],
                        'runs':            []
                    }
                # 從 config 同步 tracked_metrics 規格定義
                if cfg_metrics:
                    data_json['tracked_metrics'] = cfg_metrics
                # 用 run_id dedup：找到舊筆就更新（保留舊有非空欄位），否則 append
                _existing_idx = next(
                    (i for i, r in enumerate(data_json['runs']) if str(r.get('run_id')) == str(run_id)),
                    None
                )
                if _existing_idx is not None:
                    _old = data_json['runs'][_existing_idx]
                    for _f in ('tm_number', 'fw_version', 'pr_number', 'jira', 'asic', 'protocol', 'model'):
                        if not new_run.get(_f) and _old.get(_f):
                            new_run[_f] = _old[_f]
                    data_json['runs'][_existing_idx] = new_run
                else:
                    data_json['runs'].append(new_run)
                with open(data_json_path, 'w', encoding='utf8') as f:
                    json.dump(data_json, f, ensure_ascii=False, indent=2)
                print(f"data.json updated: {data_json_path}")

                # 注入 data.json 到 dashboard.html 並輸出到 Dashboard 資料夾
                dashboard_template = os.path.join(template_src_dir, 'dashboard.html')
                if os.path.exists(dashboard_template):
                    with open(dashboard_template, encoding='utf8') as f:
                        dash_html = f.read()
                    dash_html = dash_html.replace(
                        '/* __INJECT__ */ null',
                        json.dumps(data_json, ensure_ascii=False),
                        1
                    )
                    with open(os.path.join(dashboard_dir, 'dashboard.html'), 'w', encoding='utf8') as f:
                        f.write(dash_html)
                    print(f"dashboard.html updated: {dashboard_dir}")

            # 複製報告到共用資料夾
            reports_dir = shared_folder.get('reports', '')
            if reports_dir:
                os.makedirs(reports_dir, exist_ok=True)
                report_filename = f"{run_id}_{report_type}_Report.html"
                report_src = os.path.join(base_path, str(run_id), report_type, report_filename)
                if os.path.exists(report_src):
                    shutil.copy(report_src, os.path.join(reports_dir, report_filename))
                    print(f"Report copied to: {reports_dir}")

        except Exception as cfg_err:
            log = log + f"data.json/共用資料夾更新失敗: {str(cfg_err)}\n"
            print(f"data.json update skipped: {cfg_err}")
    # ─────────────────────────────────────────────────────────────────────

    if len(log)!=0:
        f = open(str(run_id)+"/"+report_type+"/log.txt","w", encoding='utf-8')
        f.write(log)
        f.close()
except Exception as e:
    log=log+f"Exception error on {e.__traceback__.tb_lineno} line\n"
    log=log+str(e)+"\n"
    try:
        f = open(str(run_id)+"/"+report_type+"/log.txt","w", encoding='utf-8')
        f.write(log)
        f.close()
    except:
        print("Error writing log file.")
    print("發生預期料外的錯誤，已記錄在log.txt")