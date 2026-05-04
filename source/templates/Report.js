/* --- 原本的功能 (保留) --- */
function show(elem){elem.style.display="";}
function hide(elem){elem.style.display="none";}
function style(elem, prop) {return window.getComputedStyle(elem, null)[prop];}

function check_status(status_id){
    var checkbox = document.getElementById(status_id);
    var isChecked=checkbox.checked;
    if(isChecked==true){show_data(status_id)}
    else{hide_data(status_id)}
}

function show_data(status_id){
    var tr = document.getElementsByName(status_id);
    for(var i=0; i < tr.length; i++){show(tr[i]);}
}

function hide_data(status_id){
    var tr = document.getElementsByName(status_id);
    for(var i=0; i < tr.length; i++){hide(tr[i]);}
}

window.onload=function(){
    const checkBoxes=document.querySelectorAll("input[type='checkbox']");
    for(var i=0; i < checkBoxes.length; i++) {
        if(checkBoxes[i].checked==true){show_data(checkBoxes[i].id);}
        else{hide_data(checkBoxes[i].id);}
    }
}

/* --- [新增] 切換分頁功能 --- */
function openSheet(evt, sheetName) {
    var i, tabcontent, tablinks;
    
    // 1. 隱藏所有 tabcontent (分頁內容)
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    
    // 2. 移除所有 tablinks (按鈕) 的 "active" class
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    
    // 3. 顯示目前點擊的 sheet 並加上 active class
    document.getElementById(sheetName).style.display = "block";
    evt.currentTarget.className += " active";
}