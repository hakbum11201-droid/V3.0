@echo off
setlocal enabledelayedexpansion

:: ---------------------------------------------------------
:: Orderflow Soft Score 1-Hour Net Edge Diagnostic Runner
:: ---------------------------------------------------------

:: 1. 프로젝트 루트로 이동 및 환경 설정
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONPATH=%CD%\src

echo [SYSTEM] Orderflow Soft Score 1-Hour Diagnostic Starting...
echo [SYSTEM] Analysis Duration: 3600s (1 Hour)
echo [SYSTEM] Config: configs/experiments/config_moderate.json
echo [SYSTEM] Candidate: configs/experiments/soft_score_candidate_v1.json

:: 2. 폴더 생성
if not exist "logs\experiments" mkdir "logs\experiments"
if not exist "reports\experiments" mkdir "reports\experiments"

:: 3. 기존 파일 초기화
set WS_LOG=logs\experiments\soft_score_1h_ws_events.jsonl
set OPP_JSON=reports\experiments\soft_score_1h_opportunity_diagnostics.json
set OPP_TXT=reports\experiments\soft_score_1h_opportunity_diagnostics_summary.txt
set BT_JSON=reports\experiments\soft_score_1h_backtest.json
set BT_TXT=reports\experiments\soft_score_1h_backtest_summary.txt
set SIM_JSON=reports\experiments\soft_score_1h_net_edge_sim.json
set SIM_TXT=reports\experiments\soft_score_1h_net_edge_sim_summary.txt
set DIAG_JSON=reports\experiments\soft_score_1h_net_edge_candidate_diagnostics.json
set DIAG_TXT=reports\experiments\soft_score_1h_net_edge_candidate_diagnostics_summary.txt

if exist "%WS_LOG%" del "%WS_LOG%"
if exist "%OPP_JSON%" del "%OPP_JSON%"
if exist "%BT_JSON%" del "%BT_JSON%"
if exist "%SIM_JSON%" del "%SIM_JSON%"
if exist "%DIAG_JSON%" del "%DIAG_JSON%"

:: 4. 환경 검증 (Moderate Config 기준)
echo [STEP 1] Validating Config (Moderate)...
python -m coinb.main validate-config --config configs/experiments/config_moderate.json
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Config validation failed.
    pause
    exit /b %ERRORLEVEL%
)

:: 5. 데이터 수집 (1시간)
echo [STEP 2] Collecting WS Events for 1 Hour...
python -m coinb.main collect-ws --config configs/experiments/config_moderate.json --duration 3600 --output "%WS_LOG%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] WS collection failed.
    pause
    exit /b %ERRORLEVEL%
)

:: 6. 기회 진단 (Opportunity Diagnostics)
echo [STEP 3] Running Opportunity Diagnostics...
python -m coinb.main opportunity-diagnostics --ws "%WS_LOG%" --config configs/experiments/config_moderate.json --output-json "%OPP_JSON%" --output-txt "%OPP_TXT%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Opportunity diagnostics failed.
    pause
    exit /b %ERRORLEVEL%
)

:: 7. Soft Score 백테스트
echo [STEP 4] Running Soft Score Backtest (v1)...
python -m coinb.main soft-score-backtest --opportunity "%OPP_JSON%" --candidate configs/experiments/soft_score_candidate_v1.json --output-json "%BT_JSON%" --output-txt "%BT_TXT%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Soft score backtest failed.
    pause
    exit /b %ERRORLEVEL%
)

:: 8. Net Edge 시뮬레이션
echo [STEP 5] Running Net Edge Simulation...
python -m coinb.main soft-score-net-edge-sim --opportunity "%OPP_JSON%" --backtest "%BT_JSON%" --candidate configs/experiments/soft_score_candidate_v1.json --ws "%WS_LOG%" --output-json "%SIM_JSON%" --output-txt "%SIM_TXT%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Net edge simulation failed.
    pause
    exit /b %ERRORLEVEL%
)

:: 9. 상세 진단 (MFE/MAE)
echo [STEP 6] Running Net Edge Candidate Diagnostics...
python -m coinb.main net-edge-candidate-diagnostics --opportunity "%OPP_JSON%" --backtest "%BT_JSON%" --net-edge-sim "%SIM_JSON%" --ws "%WS_LOG%" --output-json "%DIAG_JSON%" --output-txt "%DIAG_TXT%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Candidate diagnostics failed.
    pause
    exit /b %ERRORLEVEL%
)

:: 10. 결과 출력
echo.
echo =========================================================
echo [SUMMARY 1] Opportunity Diagnostics
echo =========================================================
type "%OPP_TXT%"
echo.
echo =========================================================
echo [SUMMARY 2] Soft Score Backtest
echo =========================================================
type "%BT_TXT%"
echo.
echo =========================================================
echo [SUMMARY 3] Net Edge Simulation
echo =========================================================
type "%SIM_TXT%"
echo.
echo =========================================================
echo [SUMMARY 4] Net Edge Candidate Diagnostics
echo =========================================================
type "%DIAG_TXT%"
echo.

echo [SYSTEM] All diagnostic steps completed successfully.
pause
