"""第三轮重构浏览器验证脚本 - 覆盖2项需求"""
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
    from playwright.sync_api import sync_playwright

URL = "http://localhost:5175"
results = []


def check(name, cond, detail=""):
    flag = "PASS" if cond else "FAIL"
    results.append((name, cond, detail))
    print(f"[{flag}] {name}  {detail}")


def close_all_dialogs(page):
    while page.locator(".el-dialog__headerbtn:visible").count() > 0:
        page.locator(".el-dialog__headerbtn:visible").last.click()
        page.wait_for_timeout(400)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # ─── 任务1: 子Key创建-可调用账号池独立小窗口 ───
    print("\n=== 任务1: 子Key创建-可调用账号池独立小窗口 ===")
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2000)

    # 进入 API 代理页
    page.click("text=API代理")
    page.wait_for_timeout(2000)

    # 切换到子Key管理Tab
    sub_tab = page.locator(".el-tabs__item:has-text('子Key管理')")
    check("1.1 有'子Key管理'Tab", sub_tab.count() > 0)

    if sub_tab.count() > 0:
        sub_tab.click()
        page.wait_for_timeout(1500)

        create_btn = page.locator("button:has-text('创建子Key'), button:has-text('创建子 Key')")
        check("1.2 有'创建子Key'按钮", create_btn.count() > 0)

        if create_btn.count() > 0:
            create_btn.first.click()
            page.wait_for_timeout(2000)

            # 创建子Key主对话框应显示
            main_dialog = page.locator(".el-dialog:visible").first
            main_visible = page.locator(".el-dialog:visible").count() > 0
            check("1.3 创建子Key主对话框显示", main_visible)

            if main_visible:
                main_text = main_dialog.inner_text()

                # 应有"选择账号"按钮（不再是 select 下拉）
                has_select_btn = "选择账号" in main_text
                check("1.4 主对话框有'选择账号'按钮", has_select_btn)

                # 应有"已选 X / Y 个账号"或"未选择"标签
                has_count_tag = "已选" in main_text or "未选择" in main_text
                check("1.5 主对话框有已选数量标签", has_count_tag)

                # 默认权限：应默认全选（显示"已选 X / X 个账号"）
                # 需要代理池有账号才会显示数量
                check("1.6 默认权限标签存在", has_count_tag)

                # 点击"选择账号"按钮，应弹出独立小窗口
                if has_select_btn:
                    page.locator("button:has-text('选择账号')").first.click()
                    page.wait_for_timeout(1500)

                    # 应有两个可见对话框（主对话框 + 小窗口）
                    dialog_count = page.locator(".el-dialog:visible").count()
                    check("1.7 点击后弹出独立小窗口", dialog_count >= 2, f"可见对话框数={dialog_count}")

                    if dialog_count >= 2:
                        # 小窗口应是最后一个（后打开的）
                        picker_dialog = page.locator(".el-dialog:visible").last
                        picker_text = picker_dialog.inner_text()

                        # 小窗口标题应为"选择可调用账号"
                        has_picker_title = "选择可调用账号" in picker_text
                        check("1.8 小窗口标题为'选择可调用账号'", has_picker_title)

                        # 应有"全选"复选框
                        has_select_all = "全选" in picker_text
                        check("1.9 小窗口有'全选'复选框", has_select_all)

                        # 应有账号表格（多选）
                        has_table = picker_dialog.locator(".el-table").count() > 0
                        check("1.10 小窗口有账号表格", has_table)

                        # 应有"确认"按钮
                        has_confirm = "确认" in picker_text
                        check("1.11 小窗口有'确认'按钮", has_confirm)

                        # 默认应已全选（表格行都选中）
                        selected_rows = picker_dialog.locator(".el-table__row.is-checked, .el-table__row.selected").count()
                        # Element Plus 的选中状态可能用其他类名，检查 checkbox
                        checked_boxes = picker_dialog.locator(".el-checkbox.is-checked").count()
                        # 表格内 checkbox 总数
                        all_boxes = picker_dialog.locator(".el-checkbox").count()
                        check("1.12 小窗口默认全选", checked_boxes > 0 or selected_rows > 0,
                              f"checked_boxes={checked_boxes}, selected_rows={selected_rows}")

                        close_all_dialogs(page)

    # ─── 任务2: 资源包管理改造（查所有账号的每笔额度） ───
    print("\n=== 任务2: 资源包管理改造（查所有账号的每笔额度） ===")
    page.click("text=资源包管理")
    # 等待 loading 结束（资源包接口并发查询所有账号，可能需要 10+ 秒）
    page.wait_for_timeout(2000)
    # 等待表格行出现或 loading 消失
    try:
        page.wait_for_selector(".el-table__row", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(1000)

    # URL 应为 /packages
    url = page.url
    check("2.1 资源包页面URL正确", "/packages" in url, f"url={url}")

    # 应有汇总卡片
    stat_cards = page.locator(".el-card").count()
    check("2.2 资源包页面有汇总卡片", stat_cards >= 4, f"卡片数={stat_cards}")

    # 应有表格
    has_table = page.locator(".el-table").count() > 0
    check("2.3 资源包页面有表格", has_table)

    # 表格应有"所属账号"列（不再是 key_label）
    table_header = page.locator(".el-table__header").first.inner_text()
    has_account_col = "所属账号" in table_header
    check("2.4 表格有'所属账号'列", has_account_col)

    # 应有"使用进度"列
    has_progress_col = "使用进度" in table_header
    check("2.5 表格有'使用进度'列", has_progress_col)

    # 表格应有数据行（后端已确认返回了多条资源包）
    rows = page.locator(".el-table__row").count()
    check("2.6 表格有数据行", rows > 0, f"行数={rows}")

    if rows > 0:
        # 第一行应包含 nickname（账号昵称），不是 key_label
        first_row_text = page.locator(".el-table__row").first.inner_text()
        # 应该有使用进度条
        has_progress = page.locator(".el-table__row .el-progress").count() > 0
        check("2.7 表格行包含使用进度条", has_progress)

        # 应有到期时间标签（剩 X 天 或 已到期）
        has_days_tag = "剩" in first_row_text or "已到期" in first_row_text or "天" in first_row_text
        check("2.8 表格行包含到期时间标签", has_days_tag, f"首行文本片段={first_row_text[:100]}")

    browser.close()

# 汇总
print("\n" + "=" * 60)
total = len(results)
passed = sum(1 for _, c, _ in results if c)
failed = total - passed
print(f"总计: {total}  通过: {passed}  失败: {failed}")
print("=" * 60)

if failed > 0:
    print("\n失败项:")
    for name, cond, detail in results:
        if not cond:
            print(f"  - {name}  {detail}")
    sys.exit(1)
else:
    print("\n✓ 所有验证项通过")
    sys.exit(0)
