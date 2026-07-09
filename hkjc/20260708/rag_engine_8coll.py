import json
import os
import re
import ollama

class RacingRAGEngine:
    def __init__(self, data_directory=".", target_race=None):
        self.data_dir = data_directory
        self.target_race = target_race  # 🌟 由外部傳入的場次編號，用於對齊第 8 數據集檔名
        self.kb = {}  # 知識庫索引 (Knowledge Base)
        self._initialize_knowledge_base()

    def _safe_load_json(self, filename):
        """安全讀取本地 JSON 檔案"""
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            print(f"⚠️ 警告: 找不到檔案 {filename}，該維度情報將留空。")
            return {}
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"❌ 錯誤: {filename} 解析 JSON 失敗，格式損壞。")
                return {}

    def _pad_horse_no(self, horse_str):
        """標準化馬號為雙位數字串 (e.g., '3' -> '03')"""
        if not horse_str: return ""
        # 提取數字部分
        digits = ''.join(filter(str.isdigit, str(horse_str)))
        return digits.zfill(2) if digits else ""

    def _clean_race_key(self, race_key):
        """標準化場次鍵值為統一整數 (e.g., '第 1 場' -> 1)"""
        digits = ''.join(filter(str.isdigit, str(race_key)))
        return int(digits) if digits else None

    def _initialize_knowledge_base(self):
        """
        核心 RAG 機制：加載 8 大原始數據集
        並在內存中建立以 [場次][馬號] 為 Key 的高效語義網 (Entity Linking)
        """
        print("🗄️ 正在將本地賽馬 8 大數據集載入 RAG 內存索引...")
        
        # 1. 讀取所有原始數據
        starters = self._safe_load_json("hkjc_starters_perfect.json")
        
        # 🔥【相容性升級】優先讀取優化清洗後的純淨版 JSON，找不到則回退至原版
        draws = self._safe_load_json("hkjc_all_races_draw_clean.json")
        if not draws:
            draws = self._safe_load_json("hkjc_all_races_draw.json")
            
        exceptional = self._safe_load_json("hkjc_exceptional_ultimate.json")
        trackwork = self._safe_load_json("hkjc_trackwork_perfect.json")
        vet_features = self._safe_load_json("hkjc_vet_features_v2.json")
        incidents = self._safe_load_json("hkjc_incidents_perfect.json")
        formline = self._safe_load_json("hkjc_formline_ultimate.json")
        
        # 🆕 新增第 8 數據集：馬匹歷史生涯底蘊數據 (以馬名為 Key)
        # 🌟 修正：使用 self.target_race，未指定時預設為 1
        # 🌟 檔名需與 hkjc_career_history.py 的單場輸出一致：race_{n}_career_history.json
        career_race = self.target_race if self.target_race is not None else 1
        career_history = self._safe_load_json(f"hkjc_career_history_race_{career_race}.json")

        # 2. 開始重組高維度跨表網格
        for r_raw_key, horses_list in starters.items():
            race_no = self._clean_race_key(r_raw_key)
            if not race_no: continue
            
            self.kb[race_no] = {
                "race_title": f"第 {race_no} 場賽事",
                "horses": {}
            }

            # 🔥【效能與邏輯優化】將場次模糊匹配移至外層
            matched_list = None
            for k in draws.keys():
                if r_raw_key in k:  # 當 '第 1 場' 存在於 '第 1 場 1200米 ...' 之中
                    matched_list = draws[k]
                    break
            
            exp_data = exceptional.get(r_raw_key, {})
            individual_factors = {self._pad_horse_no(h.get("馬號")): h for h in exp_data.get("個別馬匹因素", [])}
            stable_summary = exp_data.get("同廄馬匹摘要", [])
            
            track_lookup = {self._pad_horse_no(h.get("馬號")): h for h in trackwork.get(r_raw_key, [])}
            vet_lookup = {self._pad_horse_no(h.get("馬號")): h for h in vet_features.get(r_raw_key, [])}
            inc_lookup = {self._pad_horse_no(h.get("馬號")): h for h in incidents.get(r_raw_key, [])}
            past_battles = formline.get(r_raw_key, [])

            # 🌟 新增：收集場內前置型馬匹資訊，用於場級步速形勢總結
            front_runners = []  # 每項: (馬名, 檔位, 前速指標文字, 是否放頭馬)

            # 遍歷當場所有出賽馬匹，進行全維度語義化裝配
            for horse in horses_list:
                h_no = self._pad_horse_no(horse.get("馬號"))
                h_name = horse.get("馬名", "").strip()
                if not h_no: continue

                # --- A. 基礎排位特徵 (動態容錯升級版) ---
                weight = horse.get("實際負磅") or horse.get("負磅") or "未明"
                rating = horse.get("排位評分") or horse.get("評分") or "未明"
                draw_assigned = horse.get("檔位") or "未分配"
                
                # 結合 starters.json 內的隱藏高價值欄位
                recent_form = horse.get("6次近績") or horse.get("近績") or "暫無近績紀錄"
                best_time = horse.get("最佳時間") or "無歷史紀錄"

                draw_win_rate = "未知"
                draw_place_rate = "未知"
                target_draw_str = str(draw_assigned).strip()

                # 找到對應的檔位統計清單後，進行內部檔位匹配
                if matched_list and isinstance(matched_list, list):
                    for d_info in matched_list:
                        if str(d_info.get("檔位")).strip() == target_draw_str:
                            draw_win_rate = d_info.get("勝出率%") or d_info.get("勝出率 %") or d_info.get("勝出率") or d_info.get("勝率") or "未知"
                            draw_place_rate = d_info.get("上名率%") or d_info.get("上名率 %") or d_info.get("上名率") or d_info.get("上名") or "未知"
                            break

                # --- 組裝更新後的語義情報架構 ---
                semantic_profile = (
                    f"【排位基礎】: 馬號為 {h_no}，馬名為「{h_name}」。"
                    f"本仗由練馬師 {horse.get('練馬師')} 訓練，交由騎師 {horse.get('騎師')} 執韁。\n"
                    f"實際負磅為 {weight} 磅，排位評分為 {rating} 分，排在 {draw_assigned} 檔出賽。\n"
                    f"【檔位大數據】: 🎪 今日排 {draw_assigned} 檔。該跑道同檔位歷史統計 —— 歷史勝率: {draw_win_rate}，歷史上名率: {draw_place_rate}。\n"
                    f"【實力與極速】: 📊 近六仗走勢總覽: {recent_form} ； ⏱️ 同程歷史最佳時間: {best_time}。\n"
                )

                # --- 🆕 新增：【歷史底蘊】注入第 8 數據集馬匹底底襯特徵 (Entity Linking 實體對齊) ---
                career_h = career_history.get(h_name, {})
                if career_h:
                    semantic_profile += (
                        f"【歷史底蘊】: 📈 {career_h.get('生涯總結', '無數據')}\n"
                        f"              🎯 {career_h.get('級數與負磅', '無數據')}\n"
                        f"              🏃‍♂️ {career_h.get('走位風格', '無數據')}\n"
                        f"              ⚡ {career_h.get('前速指標', '無數據')}\n"
                        f"              🌦️ {career_h.get('場地偏好', '無數據')}\n"
                    )
                    # 🌟 收集前置型馬匹（放頭馬）供場級步速總結
                    style = career_h.get('走位風格', '')
                    is_front = "主動放頭馬" in style
                    front_runners.append((h_name, str(draw_assigned).strip(), career_h.get('前速指標', '無數據'), is_front))
                else:
                    semantic_profile += "【歷史底蘊】: 📅 暫無該駒歷史生涯統計，可能為在港首秀或進口新馬。\n"

                # --- B. 突變特殊因素語義轉譯 ---
                exp_h = individual_factors.get(h_no, {})
                gear_text = f"配備狀態為：{exp_h.get('配備')}" if exp_h.get('配備') else "本仗配備無變更"
                conghua_text = f"於 {exp_h.get('從化回港日期')} 從化回港備戰，具備移師從化休養回勇特徵" if exp_h.get('從化回港日期') else "全程留港本地訓練"
                rest_days = f"距離上賽已休息 {exp_h.get('上賽距今日數')} 天" if exp_h.get('上賽距今日數') else "此駒為久休復出或新馬"
                
                stable_tactic = "無同廄馬匹參戰"
                for entry in stable_summary:
                    t_horses = [self._pad_horse_no(x) for x in str(entry.get("馬號", "")).split(",") if x.strip()]
                    if h_no in t_horses:
                        stable_tactic = f"⚠️ 注意！同廄戰術暗示：練馬師 {entry.get('練馬師')} 在本場派出多駒聯手出擊（同廄聯手馬號: {entry.get('馬號')}）"
                
                semantic_profile += f"【突變因數】: {gear_text}；{conghua_text}；{rest_days}。{stable_tactic}\n"

                # --- C. 晨操快操語義轉譯 ---
                tw_h = track_lookup.get(h_no, {})
                if tw_h:
                    fast_count = len(tw_h.get("快操", []))
                    trot_count = len(tw_h.get("踱步", []))
                    trials = tw_h.get("試閘", [])
                    trial_text = f"近期進行過 {len(trials)} 次試閘，詳細試閘紀錄為 {trials}" if trials else "近期無試閘紀錄"
                    semantic_profile += f"【晨操動態】: 本賽期備戰期內，共進行了 {fast_count} 次強烈快操（拉欄/快跳），{trot_count} 次踱步慢練。{trial_text}。\n"
                else:
                    semantic_profile += "【晨操動態】: 缺少近期晨操紀錄，可能處於非正常備戰狀態。\n"

                # --- D. 獸醫傷患衍生語義 ---
                vet_h = vet_lookup.get(h_no, {})
                if vet_h and vet_h.get("傷患詳情"):
                    raw_days = vet_h.get("特徵_康復期耗時天數", -1)
                    recovery_text = "（此手術/傷患常規無須覆檢，或直接進入休養期）" if (raw_days is None or int(raw_days) < 0) else f"耗時高達 {raw_days} 天才通過檢驗"
                    semantic_profile += f"【醫療檔案】: 🛑 歷史隱患警告！該駒曾於 {vet_h.get('傷患日期')} 患有【{vet_h.get('傷患詳情')}】。 當時醫療及康復期{recovery_text}。 目前通過檢驗或距今日賽事已過去 {vet_h.get('特徵_傷患距今日數')} 天。\n"
                else:
                    semantic_profile += "【醫療檔案】: ✅ 健康紀錄完美，近期或歷史上無嚴重獸醫傷患通報。\n"

                # --- E. 歷史競賽受阻事件 ---
                inc_h = inc_lookup.get(h_no, {})
                if inc_h and inc_h.get("競賽事件摘要"):
                    semantic_profile += f"【上仗遭遇】: 🔍 實力折損還原評語：{inc_h.get('競賽事件摘要')}\n"
                else:
                    semantic_profile += "【上仗遭遇】: ⚠️ 上仗無重大競賽受阻事件回報。（注意：此處不代表其最終名次，若無提及受阻，通常代表該駒純因實力或狀態落敗，請勿過度解讀為優勢）。\n"

                # --- F. 歷史同場對壘戰績 ---
                head_to_head_logs = []
                for pb in past_battles:
                    battle_info = pb.get("歷史對壘賽事", {})
                    perf_list = pb.get("對壘馬匹表現", [])
                    for p_h in perf_list:
                        if p_h.get("馬名", "").strip() == h_name:
                            head_to_head_logs.append(f"於 {battle_info.get('日期場次')}{battle_info.get('途程')}({battle_info.get('路況')})與今日同場對手交鋒，當時背負 {p_h.get('負磅')}磅，自 {p_h.get('檔位')}檔出賽，最終跑獲第 {p_h.get('名次')} 名，獨贏賠率為 {p_h.get('賠率')}。")
                if head_to_head_logs:
                    semantic_profile += f"【歷史同場交鋒戰績】: {'；'.join(head_to_head_logs)}\n"
                else:
                    semantic_profile += "【歷史同場交鋒戰績】: 屬於新交鋒組合，無近期與同場對手直接碰頭的戰績參考。\n"

                self.kb[race_no]["horses"][h_no] = semantic_profile

            # 🌟 新增：根據場內前置型馬匹，生成【預期步速形勢演變】場級總結
            self.kb[race_no]["pace_summary"] = self._build_pace_summary(front_runners)
                
        print(f"🎉 成功！RAG 引擎已完成對齊，共裝配 {len(self.kb)} 個場次的 8 維度語義知識庫。")

    def _build_pace_summary(self, front_runners):
        """
        🌟 場級步速形勢演變總結：
        量化場內前置型（放頭）馬數量、其檔位分佈與前速指標，
        判斷是「惡性爭頂拉快步速（後追馬有利）」還是「互相禮讓（領放馬有利）」。
        front_runners: list of (馬名, 檔位, 前速指標文字, is_front_bool)
        """
        front_horses = [f for f in front_runners if f[3]]
        n_front = len(front_horses)
        n_total = len(front_runners)

        if n_total == 0:
            return "【預期步速形勢演變】: 缺乏足夠歷史走位數據，步速形勢難以判斷，建議以個體實力與檔位為主。"

        # 解析每匹前置馬的早段平均位置（從「早段平均位置 X.X」抽取）
        avg_positions = []
        for name, draw, metric, is_front in front_horses:
            m = re.search(r'早段平均位置\s*([\d.]+)', metric)
            if m:
                avg_positions.append(float(m.group(1)))

        avg_front_pos = (sum(avg_positions) / len(avg_positions)) if avg_positions else 7.0

        # 檔位分佈：大檔(外檔)被迫搶前會拉快步速
        draws = [int(d) for name, d, metric, is_front in front_horses if d.isdigit()]
        outer_draws = [d for d in draws if d >= 7]  # 外檔門檻（視總馬數，此處以 7 為界）
        inner_draws = [d for d in draws if d < 7]

        # 判斷邏輯
        if n_front >= 3:
            if outer_draws:
                verdict = (
                    f"本場共 {n_front} 隻前置型（放頭）馬，且當中 {len(outer_draws)} 隻排外檔"
                    f"（檔位 {outer_draws}），早段平均位置約 {avg_front_pos:.1f}。"
                    f"外檔放頭馬為搶佔有利位置將被迫高步速競逐，預期形成【惡性爭頂、步速偏快】之局面，"
                    f"直路後追馬（留後型）有望受惠，前領馬體力消耗風險高。"
                )
            elif inner_draws and len(inner_draws) >= 2:
                verdict = (
                    f"本場共 {n_front} 隻前置型（放頭）馬，且多集中內檔（檔位 {inner_draws}），"
                    f"早段平均位置約 {avg_front_pos:.1f}。內檔領放馬易「執到軟弱領放」互相禮讓，"
                    f"預期【步速偏慢、領放馬有利】，前領型馬可從容帶出，後追馬需克服慢步速下難追的困局。"
                )
            else:
                verdict = (
                    f"本場共 {n_front} 隻前置型（放頭）馬，早段平均位置約 {avg_front_pos:.1f}。"
                    f"多頭前置馬並存，預期早段將出現位置爭奪，步速傾向偏快，留意後追馬趁亂突圍。"
                )
        elif n_front == 1:
            verdict = (
                f"本場僅 {n_front} 隻明確前置型（放頭）馬（檔位 {draws or '未知'}），"
                f"早段平均位置約 {avg_front_pos:.1f}。預期該駒可從容領放，"
                f"【步速偏慢、單一領放馬有利】，後追馬需主動上前才不致被帶離。"
            )
        else:
            verdict = (
                f"本場前置型（放頭）馬僅 {n_front} 隻，多數馬匹傾向留後或中置，"
                f"早段平均位置約 {avg_front_pos:.1f}。預期【步速中庸、中置馬靈活走位有利】，"
                f"留後馬需視直路爆發力突圍。"
            )

        front_names = "、".join(name for name, d, m, f in front_horses) or "無"
        return (
            f"【預期步速形勢演變】: 全場 {n_total} 匹出賽，其中前置型（放頭）馬 {n_front} 隻"
            f"（{front_names}）。{verdict}"
        )

    def get_race_prompt_context(self, race_no):
        """根據場次號，提取該場所有馬匹的語義 Context"""
        race_data = self.kb.get(int(race_no))
        if not race_data:
            return f"❌ 錯誤：RAG 知識庫中未找到第 {race_no} 場的任何數據。"
        
        context_string = f"### 【RAG 精準檢索：第 {race_no} 場參賽馬匹全維度語義情報】 ###\n\n"
        # 🌟 在個體分析前先給出全局步速形勢，讓模型具備全局觀
        pace = race_data.get("pace_summary", "")
        if pace:
            context_string += pace + "\n\n"
        # 按馬號順序組裝
        for h_no in sorted(race_data["horses"].keys()):
            context_string += f"--- 馬匹編號: {h_no} ---\n"
            context_string += race_data["horses"][h_no] + "\n"
        return context_string

    def invoke_deepseek_r1(self, race_no, model_name="horse-quant"):
        """調用本地 Ollama 驅動的 DeepSeek-R1 進行預測"""
        print(f"\n🚀 RAG 檢索完成！正在喚醒本地模型 '{model_name}' 進行深度思維鏈推理...")
        
        # 1. 獲取 RAG 拼裝好的語義上下文
        rag_context = self.get_race_prompt_context(race_no)
        
        # 2. 建立 Prompt
        user_prompt = (
            f"請根據以下由 RAG 系統動態檢索出的香港賽馬精準數據，進行全維度的量化分析。\n"
            f"請務必利用你的大模型文字推理天賦，在 <think> 標籤中展現你的思考鏈（CoT），"
            f"交叉比對晨操強度與醫療代價、檔位與配備、以及上仗遭遇的實力還原。\n\n"
            f"{rag_context}\n"
            f"請開始你的專家級推理並給出最終投資結論。"
        )

        # 3. 呼叫 Ollama API 流式輸出 (Streaming)
        try:
            response = ollama.generate(
                model=model_name,
                prompt=user_prompt,
                stream=True
            )
            
            print("\n🤖 【DeepSeek-R1 推理思維鏈與預測結論】:")
            for chunk in response:
                print(chunk['response'], end='', flush=True)
            print("\n")
            
        except Exception as e:
            print(f"❌ 調用本地 Ollama 失敗，請確保 `ollama run {model_name}` 已在後台開啟。錯誤: {e}")

# --- 本地獨立測試入口 ---
if __name__ == "__main__":
    import sys  # 🛠️ 確保引入系統參數模組

    # 1. 🛠️ 從 Command Line 動態讀取場次參數（加入防錯機制）
    target_race = 1  # 設定預設場次
    
    if len(sys.argv) > 1:
        try:
            # sys.argv[1] 代表終端機輸入的第一個參數
            target_race = int(sys.argv[1])
            print(f"📥 成功讀取命令列參數：即將開始分析第 【{target_race}】 場賽事...")
        except ValueError:
            print(f"❌ 錯誤：您輸入的 '{sys.argv[1]}' 不是有效的數字！將自動切換回預設第 1 場。")
            target_race = 1
    else:
        print("💡 提示：您未在命令列輸入場次，系統自動使用預設第 【1】 場。")
        print("👉 使用提示：下次可以使用 'python rag_engine.py 3' 來直接輸出第 3 場報告。")

    print("="*60)

    # 2. 初始化 RAG 引擎（必須在 target_race 解析完成後才實例化）
    rag = RacingRAGEngine(data_directory=".", target_race=target_race)

    # 3. 獲取該場次的【全場完整語義情報】
    full_context = rag.get_race_prompt_context(target_race)
    
    # 4. 直接寫入本地的 txt 檔案
    output_filename = f"race_{target_race}_report.txt"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(full_context)
        
    print(f"\n🎉 成功！第 {target_race} 場的全場完整語義報告已生成。")
    print(f"💾 檔案已儲存至: '{output_filename}'")
    print(f"💡 提示：請直接去資料夾打開這個文字檔，全選複製後貼給大模型即可！")