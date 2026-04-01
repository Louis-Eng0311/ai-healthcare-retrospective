import React from "react";

const pageStyle = {
  minHeight: "100vh",
  color: "#183153",
  fontFamily:
    '"Pretendard Variable", "Pretendard", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
  background:
    "radial-gradient(circle at top left, rgba(31, 95, 209, 0.12), transparent 28%), linear-gradient(180deg, #f8fbff 0%, #f2f6fb 100%)",
};

const wrapStyle = {
  width: "min(1160px, calc(100% - 32px))",
  margin: "0 auto",
};

const buttonBaseStyle = {
  minHeight: "46px",
  padding: "0 20px",
  borderRadius: "999px",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  fontWeight: 700,
  textDecoration: "none",
  border: "1px solid transparent",
};

function LandingPage() {
  const featureCards = [
    [
      "복약 체크",
      "아침, 점심, 저녁, 취침 전 복약 일정을 시간대별로 확인하고 기록할 수 있습니다.",
    ],
    [
      "병원 일정 관리",
      "중요한 병원 방문 일정을 등록하고 알림으로 놓치지 않도록 돕습니다.",
    ],
    [
      "처방전 OCR",
      "처방전을 업로드하면 약 정보를 인식해 복약 관리 흐름으로 연결할 수 있습니다.",
    ],
    [
      "AI 복약 가이드",
      "어려운 약 정보를 더 이해하기 쉬운 안내 형태로 확인할 수 있습니다.",
    ],
  ];

  const infoCards = [
    [
      "복약자",
      "오늘 먹어야 할 약을 시간대별로 확인하고 바로 기록할 수 있습니다.",
    ],
    [
      "보호자",
      "복약 상태와 병원 일정을 함께 확인하고, 리만인드 할 수 있습니다.",
    ],
    [
      "문서와 가이드",
      "처방전 업로드부터 AI 복약 가이드 확인까지 한 흐름으로 이어집니다.",
    ],
  ];

  return (
    <div style={pageStyle}>
      <div style={wrapStyle}>
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "16px",
            padding: "26px 0",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            <span
              style={{
                width: "44px",
                height: "44px",
                borderRadius: "15px",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: "linear-gradient(135deg, #1f5fd1 0%, #73a9ff 100%)",
                color: "#fff",
                fontWeight: 800,
              }}
            >
              CB
            </span>
            <div>
              <div style={{ fontWeight: 800, fontSize: "1.1rem" }}>케어브릿지</div>
              <div style={{ color: "#62748d", fontSize: "0.92rem" }}>
                복약자와 보호자를 연결하는 건강 관리 서비스
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <a
              href="/login"
              style={{
                ...buttonBaseStyle,
                background: "#fff",
                borderColor: "#d8e2ef",
                color: "#183153",
              }}
            >
              로그인
            </a>
            <a
              href="/signup"
              style={{
                ...buttonBaseStyle,
                background: "#1f5fd1",
                borderColor: "#1f5fd1",
                color: "#fff",
                boxShadow: "0 10px 24px rgba(31, 95, 209, 0.24)",
              }}
            >
              회원가입
            </a>
          </div>
        </header>

        <main style={{ padding: "14px 0 64px" }}>
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.05fr) minmax(360px, 0.95fr)",
              gap: "28px",
              alignItems: "center",
            }}
          >
            <div>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  padding: "9px 14px",
                  borderRadius: "999px",
                  background: "rgba(31, 95, 209, 0.09)",
                  color: "#123b86",
                  fontWeight: 700,
                  fontSize: "0.92rem",
                }}
              >
                복약과 병원 일정을 한 흐름으로 관리하는 연결 서비스
              </span>
               <h1
                 style={{
                   margin: "18px 0 16px",
                   maxWidth: "18ch",
                   fontSize: "clamp(1.8rem, 3.8vw, 3.2rem)",
                   lineHeight: 1.12,
                   letterSpacing: "-0.04em",
                   wordBreak: "keep-all",
                 }}
               >
                혼자 챙기기 버거운 건강 관리,
                <br />
                함께 보기 쉽게 만들었습니다
              </h1>
              <p
                style={{
                  maxWidth: "620px",
                  margin: 0,
                  color: "#62748d",
                  fontSize: "1.08rem",
                  lineHeight: 1.8,
                }}
              >
                케어브릿지는 복약자와 보호자가 같은 흐름을 보며
                <br />
                복약, 병원 일정, 처방전 정보와 AI 가이드를 함께 확인할 수 있도록 구성된 서비스입니다.

              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginTop: "28px" }}>
                <a
                  href="/signup"
                  style={{
                    ...buttonBaseStyle,
                    background: "#1f5fd1",
                    borderColor: "#1f5fd1",
                    color: "#fff",
                    boxShadow: "0 10px 24px rgba(31, 95, 209, 0.24)",
                  }}
                >
                  지금 시작하기
                </a>
                <a
                  href="/login"
                  style={{
                    ...buttonBaseStyle,
                    background: "#fff",
                    borderColor: "#d8e2ef",
                    color: "#183153",
                  }}
                >
                  로그인
                </a>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "24px" }}>
                {["복약 체크", "병원 일정 알림", "처방전 OCR", "AI 복약 가이드"].map((label) => (
                  <span
                    key={label}
                    style={{
                      padding: "9px 13px",
                      borderRadius: "999px",
                      background: "#fff",
                      border: "1px solid #d8e2ef",
                      color: "#62748d",
                      fontSize: "0.92rem",
                    }}
                  >
                    {label}
                  </span>
                ))}
              </div>
            </div>

            <div
              style={{
                position: "relative",
                overflow: "hidden",
                borderRadius: "34px",
                padding: "28px",
                background:
                  "linear-gradient(160deg, rgba(18, 59, 134, 0.98) 0%, rgba(31, 95, 209, 0.96) 62%, rgba(38, 169, 122, 0.90) 100%)",
                color: "#fff",
                boxShadow: "0 18px 40px rgba(20, 33, 61, 0.08)",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  right: "-40px",
                  bottom: "-40px",
                  width: "220px",
                  height: "220px",
                  borderRadius: "50%",
                  background: "rgba(255,255,255,0.08)",
                }}
              />
              <img
                src="/mascot.png"
                alt="케어브릿지 마스코트"
                style={{
                  position: "relative",
                  zIndex: 1,
                  width: "min(100%, 320px)",
                  display: "block",
                  margin: "6px auto 18px",
                  filter: "drop-shadow(0 18px 32px rgba(7, 18, 42, 0.28))",
                }}
              />
              <h2 style={{ position: "relative", zIndex: 1, margin: "0 0 10px", fontSize: "1.35rem" }}>
                매일 확인해야 하는 건강 정보를 한 화면에
              </h2>
              <p style={{ position: "relative", zIndex: 1, margin: 0, color: "rgba(255,255,255,0.82)", lineHeight: 1.75 }}>
                약을 먹었는지, 병원 일정이 언제인지, 처방전 내용이 무엇인지
                <br />
                따로 흩어져 있으면 놓치기 쉽습니다.
                <br />
                케어브릿지는 이 흐름을 한곳에 모아 더 쉽게 확인하고 이해할 수 있도록 구성했습니다.
              </p>
              <div style={{ position: "relative", zIndex: 1, display: "grid", gap: "12px", marginTop: "18px" }}>
                {infoCards.map(([title, description]) => (
                  <div
                    key={title}
                    style={{
                      padding: "14px 16px",
                      borderRadius: "18px",
                      background: "rgba(255,255,255,0.12)",
                    }}
                  >
                    <strong style={{ display: "block", marginBottom: "6px" }}>{title}</strong>
                    <div style={{ color: "rgba(255,255,255,0.82)", lineHeight: 1.7 }}>{description}</div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section style={{ padding: "32px 0" }}>
            <h2 style={{ fontSize: "2rem", marginBottom: "12px" }}>케어브릿지에서 할 수 있는 일</h2>
            <p style={{ color: "#62748d", lineHeight: 1.7, marginBottom: "24px" }}>
              복약부터 일정, 문서 확인까지 한곳에서 관리할 수 있습니다.
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "18px",
              }}
            >
              {featureCards.map(([title, description]) => (
                <article
                  key={title}
                  style={{
                    padding: "24px",
                    border: "1px solid #d8e2ef",
                    borderRadius: "24px",
                    background: "#fff",
                    boxShadow: "0 12px 28px rgba(20, 33, 61, 0.05)",
                  }}
                >
                  <h3 style={{ marginTop: 0 }}>{title}</h3>
                  <p style={{ color: "#62748d", lineHeight: 1.65, marginBottom: 0 }}>{description}</p>
                </article>
              ))}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

export default LandingPage;
