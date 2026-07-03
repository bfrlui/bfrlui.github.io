# 技能：香港賽馬會自動抓取與預測

## 描述
根據使用者輸入的日期與場次，自動拼接香港賽馬會的官方網址，擷取資料來源網址，並分析預測結果。

## 輸入
- 賽事日期（YYYY/MM/DD）
- 賽事編號（整數）

## 資料來源
- 排位表資料網址模板：  
  `https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={賽事日期}&Racecourse={Racecourse}&RaceNo={賽事編號}`  

- 馬匹資料網址模板：  
  `https://racing.hkjc.com/zh-hk/local/information/horse?HorseNo={馬匹編號}`  

- 晨操資料網址模板：  
  `https://racing.hkjc.com/zh-hk/local/information/trackworkresult?horseid={馬匹編號}`  
  `https://racing.hkjc.com/zh-hk/local/information/localtrackwork?racedate=2026/07/04&Racecourse=ST&RaceNo=1`

- 所有往績網址模板：  
  `https://racing.hkjc.com/zh-hk/local/information/horse?horseid={馬匹編號}&Option=1`  

- 途程賽績網址模板：  
  `https://racing.hkjc.com/zh-hk/local/information/performance?horseid={馬匹編號}&view=Percentage`  

- 傷患記錄網址模板：  
  `https://racing.hkjc.com/zh-hk/local/information/ovehorse?horseid={馬匹編號}`  

- 即時賠率網址模板（僅限賽事日）：  
  `https://bet.hkjc.com/ch/racing/wp/{賽事日期}/{Racecourse}/{賽事編號}`  

- 練馬師統計網址：  
  `https://racing.hkjc.com/zh-hk/local/information/tncstat`  

- 騎師統計網址：  
  `https://racing.hkjc.com/zh-hk/local/information/jkcstat`  

- 騎師大熱統計網址：  
  `https://racing.hkjc.com/zh-hk/local/information/jockeyfavourite`  

- 練馬師大熱統計網址：  
  `https://racing.hkjc.com/zh-hk/local/information/trainerfavourite`  

- 跑道資料網址：  
  `https://racing.hkjc.com/zh-hk/local/page/racing-course`  

- 天氣及跑道狀況網址：  
  `https://racing.hkjc.com/zh-hk/local/info/windtracker`  

- 檔位統計網址：  
  `https://racing.hkjc.com/zh-hk/local/information/draw`  

> 其中：
> - `{賽事日期}` → 例如 `2026/06/13`  
> - `{Racecourse}` → 根據賽事地點，沙田=`ST` 或 跑馬地=`HV`
> - `{賽事編號}` → 1, 2, 3...
> - `{馬匹編號}` → 例如 `HK_2025_L051`


## 輸出
- 實事資訊
- Markdown 表格，包含：
  - 出賽馬號
  - 馬匹名稱 + 馬匹編號 
  - 預測排名
  - 信心分數
  - 分析摘要（包含排位表、馬匹資料、晨操表現、所有往績、途程賽績、傷患記錄、練馬師統計、騎師統計、騎師大熱統計、練馬師大熱統計、跑道資料、天氣跑道狀況與檔位統計；若有即時賠率則一併納入）
- 儲存檔案名稱：`賽事日期-賽事編號.md`

> 其中：
> - 出賽馬號 是即時賠率網址中的`馬號`
> - 信心分數 以百分比打分

## 提示模板
你是一位專業的賽馬分析師。  
請自動使用「賽事日期」與「賽事編號」拼接香港賽馬會的官方網址，擷取該場比賽的排位表、馬匹資料、晨操表現、所有往績、途程賽績、傷患記錄、練馬師統計、騎師統計、騎師大熱統計、練馬師大熱統計、跑道資料、天氣跑道狀況與檔位統計，並在賽事日額外加入即時賠率。  
輸出必須是 Markdown 表格。以預測排名排序，確保全部輸出內容必須是中文，尤其馬匹名稱。  
將結果儲存為 `賽事日期-賽事編號.md`。
