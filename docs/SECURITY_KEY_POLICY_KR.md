# V3.0 API Key / Security Policy

## 1. 기본 원칙
- 기본 실행은 Keyless Paper Mode이다.
- API Key 없이 RUN_COINB_ALL.bat, paper_engine, Streamlit UI가 정상 작동해야 한다.
- 업비트 API Key는 Access Key + Secret Key 한 쌍이다.
- Secret Key는 발급 시에만 확인 가능하므로 절대 외부에 노출하지 않는다.
- GitHub에 .env, .env.account, .env.live 파일을 올리지 않는다.
- GitHub에는 .env.example, .env.account.example, .env.live.example만 올린다.

## 2. 키 분리 원칙
- 조회 전용 키와 주문용 키를 분리한다.
- 조회 전용 키는 .env.account에서만 사용한다.
- 주문용 키는 나중에 tiny_live 단계에서만 .env.live로 분리 사용한다.
- 출금 권한 키는 절대 만들지 않는다.
- 주문 권한 키는 허용 IP 등록을 필수로 한다.
- LIVE_TRADING_ENABLED=false 또는 TINY_LIVE_APPROVED=false이면 주문이 불가능해야 한다.
- DDM이 BLOCK_NEW_ENTRY 또는 DATA_ERROR 상태이면 신규 주문은 불가능해야 한다.

## 3. GitHub 보안 원칙
- 실제 키가 들어간 파일은 절대 커밋하지 않는다.
- 커밋 전 secret_guard 검사를 수행한다.
- GitHub Secret Scanning / Push Protection 활성화를 권장한다.
- 키가 한 번이라도 GitHub에 올라갔다면 즉시 폐기하고 재발급한다.

## 4. 해킹 방어 원칙
- Streamlit UI는 기본적으로 localhost 전용으로 사용한다.
- 외부 접속, 포트포워딩, 공유기 DMZ 사용을 금지한다.
- 원격 접속이 필요하면 VPN 또는 신뢰 가능한 원격 데스크톱만 사용한다.
- 공용 Wi-Fi에서 실거래 모드를 사용하지 않는다.
- Windows Defender 또는 백신을 활성화한다.
- Windows 계정 비밀번호를 사용한다.
- GitHub, Google, Upbit 계정은 2단계 인증을 사용한다.
- API Key 파일은 클라우드 동기화 폴더에 두지 않는다.
- 화면 공유나 스크린샷에 Key, .env, 계좌 정보가 보이지 않게 한다.
- AI 도구에는 .env, logs, reports, runtime, data 폴더를 컨텍스트로 주지 않는다.
- 로그 파일에 Access Key, Secret Key, JWT, Authorization Header를 기록하지 않는다.
- 오류 메시지에도 민감정보를 출력하지 않는다.

## 5. 침해 의심 시 대응
- 즉시 STOP_COINB_ALL.bat를 실행한다.
- 업비트 API Key를 삭제한다.
- 새 API Key를 재발급한다.
- GitHub에 키가 올라갔는지 확인한다.
- 키가 노출되었다면 해당 키는 재사용하지 않는다.
- PC 악성코드 검사를 수행한다.
- GitHub, Google, Upbit 비밀번호와 2FA 상태를 확인한다.
