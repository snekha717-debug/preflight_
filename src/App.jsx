// src/App.jsx
import React, { useState, useEffect, useRef } from "react";

// src/App.jsx
const API_BASE =
  window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : "/api";

const CATEGORY_COLORS = {
  banned_word: "bg-red-50 text-red-700 border-red-200",
  required_phrase: "bg-purple-50 text-purple-700 border-purple-200",
  tone: "bg-amber-50 text-amber-700 border-amber-200",
  messaging: "bg-blue-50 text-blue-700 border-blue-200",
  claim: "bg-rose-50 text-rose-700 border-rose-200",
};

const SEVERITY_BADGES = {
  critical: "bg-red-600 text-white",
  warning: "bg-amber-500 text-white",
  minor: "bg-slate-500 text-white",
};

export default function App() {
  const [currentView, setCurrentView] = useState("dashboard"); // 'dashboard' | 'guidelines' | 'rules' | 'history'
  const [contentType, setContentType] = useState("copy"); // 'copy' | 'image'
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Guideline & Rules State
  const [guidelines, setGuidelines] = useState([]);
  const [activeGuideline, setActiveGuideline] = useState(null);
  const [ruleFilter, setRuleFilter] = useState("all");

  // Content Check State
  const [purpose, setPurpose] = useState("Announce a product launch to enterprise clients");
  const [marketingContent, setMarketingContent] = useState(
    "Unlock unprecedented hyper-growth with our revolutionary, ground-breaking AI solution. We guarantee 10x ROI overnight, crushing the outdated competition without compromise! Join 100,000+ top enterprises that blindly trust our proprietary cloud algorithms to dominate their industry."
  );
  const [auditResult, setAuditResult] = useState(null);

  // Review History & Benchmark State
  const [historyList, setHistoryList] = useState([]);
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [showBenchmarkModal, setShowBenchmarkModal] = useState(false);

  const fileInputRef = useRef(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  async function loadInitialData() {
    try {
      const res = await fetch(`${API_BASE}/guidelines`);
      if (res.ok) {
        const data = await res.json();
        setGuidelines(data);
        if (data.length > 0) {
          fetchGuidelineDetails(data[0].id);
        }
      }
      fetchHistory();
    } catch {
      setErrorMsg("FastAPI backend is offline at " + API_BASE);
    }
  }

  async function fetchGuidelineDetails(id) {
    try {
      const res = await fetch(`${API_BASE}/guidelines/${id}`);
      if (res.ok) {
        const detail = await res.json();
        setActiveGuideline(detail);
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchHistory() {
    try {
      const res = await fetch(`${API_BASE}/checks`);
      if (res.ok) {
        const list = await res.json();
        setHistoryList(list);
      }
    } catch (err) {
      console.error(err);
    }
  }

  // 1. BETTER PDF READING & APPROVAL ACTIONS
  async function handlePdfUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setErrorMsg("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("name", file.name.replace(/\.pdf$/i, ""));
      const res = await fetch(`${API_BASE}/guidelines/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("PDF processing failed");
      const created = await res.json();
      await loadInitialData();
      await fetchGuidelineDetails(created.id);
      setCurrentView("rules");
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadDemoPdf() {
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(`${API_BASE}/guidelines/load-demo`, { method: "POST" });
      if (!res.ok) throw new Error("Failed to load demo PDF");
      const created = await res.json();
      await loadInitialData();
      await fetchGuidelineDetails(created.id);
      setCurrentView("rules");
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleRuleStatus(ruleId, newStatus) {
    try {
      const res = await fetch(`${API_BASE}/rules/${ruleId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved: newStatus }),
      });
      if (res.ok && activeGuideline) {
        await fetchGuidelineDetails(activeGuideline.id);
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function handleBulkApprove(status) {
    if (!activeGuideline) return;
    try {
      await fetch(`${API_BASE}/guidelines/${activeGuideline.id}/approve-all?approved=${status}`, {
        method: "POST",
      });
      await fetchGuidelineDetails(activeGuideline.id);
    } catch (err) {
      console.error(err);
    }
  }

  // 2. BETTER CONTENT CHECKING ACTIONS
  async function handleCheckContent() {
    if (!activeGuideline) {
      setErrorMsg("Please upload or select a brand guideline first.");
      return;
    }
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(`${API_BASE}/check-content`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guideline_id: activeGuideline.id,
          content_title: purpose || "Marketing Copy",
          text: marketingContent,
          only_approved_rules: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Content check failed");
      setAuditResult(data);
      fetchHistory();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleApplyFix(issue) {
    if (!issue.suggested_replacement) return;
    let updated = marketingContent;
    if (issue.offending_text && issue.offending_text !== "(Missing from content)") {
      updated = updated.replace(new RegExp(issue.offending_text, "i"), issue.suggested_replacement);
    } else if (issue.category === "required_phrase") {
      updated = updated.trim() + "\n\n" + issue.suggested_replacement;
    }
    setMarketingContent(updated);

    if (auditResult) {
      const newIssues = auditResult.issues.filter((i) => i !== issue);
      setAuditResult({
        ...auditResult,
        issues: newIssues,
        overall_score: Math.min(100, auditResult.overall_score + 15),
      });
    }
  }

  // 3. TESTING & BENCHMARK ACTIONS
  async function handleRunBenchmark() {
    if (!activeGuideline) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/benchmark/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guideline_id: activeGuideline.id }),
      });
      const data = await res.json();
      setBenchmarkData(data);
      setShowBenchmarkModal(true);
      fetchHistory();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  }

  function downloadReport(checkId, format = "md") {
    window.open(`${API_BASE}/reports/${checkId}/download?format=${format}`, "_blank");
  }

  const approvedRulesCount = (activeGuideline?.rules || []).filter((r) => r.approved === 1).length;
  const wordCount = marketingContent.trim() ? marketingContent.trim().split(/\s+/).length : 0;
  const charCount = marketingContent.length;

  const filteredRules = (activeGuideline?.rules || []).filter((r) => {
    if (ruleFilter === "all") return true;
    if (ruleFilter === "approved") return r.approved === 1;
    if (ruleFilter === "pending") return r.approved === 0;
    return r.category === ruleFilter;
  });

  return (
    <div className="flex min-h-screen bg-[#f8fafc] text-slate-800 font-sans">
      {/* ----------------- LEFT SIDEBAR (ORIGINAL UI) ----------------- */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col justify-between p-4 shrink-0">
        <div className="space-y-6">
          {/* Logo & Badge */}
          <div className="flex items-center gap-2.5 px-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-sm">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-900 text-lg tracking-tight">Preflight</span>
              <span className="text-[10px] bg-blue-50 text-blue-600 font-bold px-1.5 py-0.5 rounded border border-blue-200 tracking-wider">
                AI AUDITOR
              </span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1">
            <button
              onClick={() => setCurrentView("dashboard")}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                currentView === "dashboard"
                  ? "bg-blue-50 text-blue-600 font-semibold"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              <span>Dashboard</span>
            </button>

            <button
              onClick={() => setCurrentView("guidelines")}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                currentView === "guidelines"
                  ? "bg-blue-50 text-blue-600 font-semibold"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span>Brand Guidelines</span>
            </button>

            <button
              onClick={() => setCurrentView("rules")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                currentView === "rules"
                  ? "bg-blue-50 text-blue-600 font-semibold"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <div className="flex items-center gap-3">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
                <span>Brand Rules</span>
              </div>
              <span className="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full font-semibold">
                {approvedRulesCount}
              </span>
            </button>

            <button
              onClick={() => setCurrentView("history")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                currentView === "history"
                  ? "bg-blue-50 text-blue-600 font-semibold"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <div className="flex items-center gap-3">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Review History</span>
              </div>
              <span className="bg-slate-100 text-slate-600 text-xs px-2 py-0.5 rounded-full font-medium">
                {historyList.length}
              </span>
            </button>
          </nav>
        </div>

        {/* Bottom Sidebar Widget */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs space-y-1">
          <div className="flex items-center justify-between font-bold text-slate-800">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Preflight Engine
            </span>
            <span className="text-[10px] text-emerald-600 font-semibold">• Live</span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Audits marketing copy and creative images against approved compliance rules.
          </p>
        </div>
      </aside>

      {/* ----------------- MAIN WORKSPACE CONTENT ----------------- */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header Breadcrumbs & Status */}
        <header className="h-16 bg-white border-b border-slate-200 px-8 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>Workspace</span>
            <span>&gt;</span>
            <span className="font-semibold text-slate-800 capitalize">{currentView}</span>
          </div>

          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-500 font-mono">FastAPI backend at /api</span>
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-full text-xs font-medium text-slate-700">
              <span className="w-2 h-2 rounded-full bg-blue-600" />
              <span>Global Marketing Team</span>
            </div>
          </div>
        </header>

        {/* Main View Area */}
        <main className="p-8 max-w-5xl w-full mx-auto space-y-6">
          {errorMsg && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-xs flex justify-between items-center">
              <span>{errorMsg}</span>
              <button onClick={() => setErrorMsg("")} className="font-bold underline cursor-pointer">
                Dismiss
              </button>
            </div>
          )}

          {/* =========================================================
              VIEW 1: DASHBOARD (MAIN CONTENT CHECKER)
          ========================================================= */}
          {currentView === "dashboard" && (
            <div className="space-y-6">
              {/* Header Titles + Mode Switcher */}
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                    Check your content before publishing.
                  </h1>
                  <p className="text-sm text-slate-500 mt-1">
                    Scan copy or visual creatives against approved brand tone, banned words, and claims rules.
                  </p>
                </div>

                <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-semibold">
                  <button
                    onClick={() => setContentType("copy")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition cursor-pointer ${
                      contentType === "copy" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span>Marketing Copy</span>
                  </button>
                  <button
                    onClick={() => setContentType("image")}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition cursor-pointer ${
                      contentType === "image" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <span>Creative Image</span>
                  </button>
                </div>
              </div>

              {/* Main Checker Box (Original UI Card) */}
              <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    CONTENT PURPOSE / CONTEXT
                  </label>
                  <input
                    type="text"
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                    placeholder="e.g. Announce a product launch to enterprise clients"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3.5 py-2 text-sm text-slate-800 focus:outline-none focus:bg-white focus:border-blue-500"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-400">
                      MARKETING CONTENT
                    </label>
                    <span className="text-xs text-slate-400">
                      {wordCount} words • {charCount} characters
                    </span>
                  </div>
                  <textarea
                    rows={6}
                    value={marketingContent}
                    onChange={(e) => setMarketingContent(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3.5 text-sm text-slate-800 leading-relaxed focus:outline-none focus:bg-white focus:border-blue-500"
                  />
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1">
                    <span>Evaluates against {approvedRulesCount} approved brand rules and saves to database.</span>
                    <button
                      onClick={() => setMarketingContent("")}
                      className="hover:underline cursor-pointer"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <button
                    onClick={() =>
                      setMarketingContent(
                        "Unlock unprecedented hyper-growth with our revolutionary, ground-breaking AI solution. We guarantee 10x ROI overnight, crushing the outdated competition without compromise! Join 100,000+ top enterprises that blindly trust our proprietary cloud algorithms to dominate their industry."
                      )
                    }
                    className="text-xs text-blue-600 hover:underline font-medium cursor-pointer"
                  >
                    Reset with example text
                  </button>

                  <button
                    onClick={handleCheckContent}
                    disabled={loading}
                    className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-5 py-2.5 rounded-lg text-sm flex items-center gap-2 cursor-pointer shadow-sm transition"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <span>{loading ? "Auditing Content..." : "Check Content"}</span>
                  </button>
                </div>
              </div>

              {/* Audit Results Card (Preserving Original Look & Adding Round 2 Diagnostic Fixes) */}
              {auditResult && (
                <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs space-y-6">
                  {/* Score & Summary Header */}
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div className="flex items-center gap-4">
                      <div
                        className={`w-14 h-14 rounded-xl flex flex-col items-center justify-center font-bold text-white shadow-inner ${
                          auditResult.status === "PASS"
                            ? "bg-emerald-600"
                            : auditResult.status === "NEEDS_REVISION"
                            ? "bg-amber-500"
                            : "bg-red-600"
                        }`}
                      >
                        <span className="text-xl leading-none">{auditResult.overall_score}</span>
                        <span className="text-[10px] uppercase opacity-80">/100</span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-xs font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                              auditResult.status === "PASS"
                                ? "bg-emerald-100 text-emerald-800"
                                : auditResult.status === "NEEDS_REVISION"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {auditResult.status}
                          </span>
                          <span className="text-xs text-slate-500">
                            Found {auditResult.issues?.length || 0} issue(s) across {auditResult.active_rules_count} active rules
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 mt-1">{auditResult.summary}</p>
                      </div>
                    </div>

                    {/* Downloadable Reports Dropdown (Round 3) */}
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => downloadReport(auditResult.id, "md")}
                        className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-2.5 py-1.5 rounded cursor-pointer"
                        title="Download Markdown Report"
                      >
                        ↓ .MD Report
                      </button>
                      <button
                        onClick={() => downloadReport(auditResult.id, "html")}
                        className="border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold px-2.5 py-1.5 rounded cursor-pointer"
                        title="Download HTML Report"
                      >
                        ↓ .HTML
                      </button>
                      <button
                        onClick={() => downloadReport(auditResult.id, "csv")}
                        className="border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold px-2.5 py-1.5 rounded cursor-pointer"
                        title="Download CSV"
                      >
                        ↓ .CSV
                      </button>
                    </div>
                  </div>

                  {/* Diagnostic Findings with Severity, Explanation & 1-Click Fixes */}
                  <div className="space-y-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                      DETECTED BRAND COMPLIANCE ISSUES ({auditResult.issues?.length || 0})
                    </h3>

                    {auditResult.issues?.length === 0 ? (
                      <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs font-medium">
                        ✓ All brand rules passed! No banned words, missing phrases, or claims issues found.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {auditResult.issues.map((issue, idx) => (
                          <div
                            key={idx}
                            className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-2"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                                    SEVERITY_BADGES[issue.severity] || SEVERITY_BADGES.warning
                                  }`}
                                >
                                  {issue.severity}
                                </span>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${CATEGORY_COLORS[issue.category]}`}>
                                  {issue.category?.replace("_", " ")}
                                </span>
                                <span className="font-bold text-slate-800">{issue.title}</span>
                              </div>
                              <span className="text-[11px] text-slate-400">
                                Rule Source: Page {issue.page_number} ({issue.section_title})
                              </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-slate-600 pt-1">
                              <div>
                                <span className="font-semibold text-slate-700">What is wrong: </span>
                                <span>{issue.what_is_wrong}</span>
                              </div>
                              <div>
                                <span className="font-semibold text-slate-700">How to fix: </span>
                                <span>{issue.how_to_fix}</span>
                              </div>
                            </div>

                            <div className="bg-white p-2.5 rounded border border-slate-200 flex items-center justify-between gap-4 mt-1">
                              <span className="italic text-slate-500 text-[11px] truncate">
                                Provenance Quote: "{issue.source_quote}"
                              </span>
                              {issue.suggested_replacement && (
                                <button
                                  onClick={() => handleApplyFix(issue)}
                                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs px-3 py-1 rounded shrink-0 cursor-pointer"
                                >
                                  Apply Fix: "{issue.suggested_replacement}"
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* =========================================================
              VIEW 2: BRAND GUIDELINES (MULTI-PAGE UPLOAD & SUMMARY)
          ========================================================= */}
          {currentView === "guidelines" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Brand Guidelines</h1>
                  <p className="text-sm text-slate-500 mt-1">
                    Upload brand guidelines PDFs. Preflight reads longer documents, segments chapters, and extracts rules with exact page citations.
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept=".pdf"
                    onChange={handlePdfUpload}
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-4 py-2.5 rounded-lg cursor-pointer"
                  >
                    {loading ? "Reading PDF..." : "Upload Brand Guideline PDF"}
                  </button>
                  <button
                    onClick={handleLoadDemoPdf}
                    className="border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold px-4 py-2.5 rounded-lg cursor-pointer"
                  >
                    + Load 4-Page Demo PDF
                  </button>
                </div>
              </div>

              {/* Guidelines List */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {guidelines.map((g) => (
                  <div
                    key={g.id}
                    onClick={() => fetchGuidelineDetails(g.id)}
                    className={`p-5 rounded-xl border bg-white cursor-pointer transition ${
                      activeGuideline?.id === g.id
                        ? "border-blue-500 ring-2 ring-blue-100"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-bold text-sm text-slate-900">{g.name}</h3>
                      <span className="text-[10px] font-bold bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                        {g.total_pages} Pages Parsed
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mb-3 truncate">{g.filename}</p>
                    <div className="flex items-center justify-between text-xs pt-3 border-t border-slate-100">
                      <span className="text-slate-600">
                        {g.approved_rules} of {g.total_rules} rules approved
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          fetchGuidelineDetails(g.id);
                          setCurrentView("rules");
                        }}
                        className="text-blue-600 font-semibold hover:underline"
                      >
                        Inspect Rules →
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* =========================================================
              VIEW 3: BRAND RULES (PROVENANCE & USER APPROVAL)
          ========================================================= */}
          {currentView === "rules" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Brand Rules & Approval</h1>
                  <p className="text-sm text-slate-500 mt-1">
                    Review where each rule came from in the PDF and approve rules before they are used for content checking.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleBulkApprove(1)}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-3 py-2 rounded-lg cursor-pointer"
                  >
                    Approve All Rules
                  </button>
                  <button
                    onClick={() => handleBulkApprove(0)}
                    className="bg-slate-200 hover:bg-slate-300 text-slate-700 text-xs font-semibold px-3 py-2 rounded-lg cursor-pointer"
                  >
                    Reset to Pending
                  </button>
                </div>
              </div>

              {/* Filter Tabs */}
              <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
                {["all", "approved", "pending", "banned_word", "required_phrase", "tone", "messaging", "claim"].map((f) => (
                  <button
                    key={f}
                    onClick={() => setRuleFilter(f)}
                    className={`text-xs px-3 py-1.5 rounded-lg font-medium cursor-pointer ${
                      ruleFilter === f
                        ? "bg-blue-600 text-white"
                        : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    {f.replace("_", " ").toUpperCase()}
                  </button>
                ))}
              </div>

              {/* Rules List with Provenance */}
              <div className="space-y-3">
                {filteredRules.map((rule) => (
                  <div
                    key={rule.id}
                    className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex items-center justify-between gap-4"
                  >
                    <div className="space-y-1.5 flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${CATEGORY_COLORS[rule.category]}`}>
                          {rule.category?.replace("_", " ")}
                        </span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${SEVERITY_BADGES[rule.severity]}`}>
                          {rule.severity}
                        </span>
                        <span className="text-xs text-slate-500 font-medium">
                          Page {rule.page_number} • {rule.section_title}
                        </span>
                      </div>
                      <p className="text-sm font-semibold text-slate-900">{rule.rule_text}</p>
                      <p className="text-xs text-slate-500 italic bg-slate-50 p-2 rounded border border-slate-100">
                        Source Quote: "{rule.source_quote}"
                      </p>
                    </div>

                    {/* Rule Approval Switches */}
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleToggleRuleStatus(rule.id, 1)}
                        className={`text-xs px-3 py-1.5 rounded-md font-semibold border cursor-pointer ${
                          rule.approved === 1
                            ? "bg-emerald-600 text-white border-emerald-600"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-emerald-50"
                        }`}
                      >
                        {rule.approved === 1 ? "✓ Approved" : "Approve"}
                      </button>
                      <button
                        onClick={() => handleToggleRuleStatus(rule.id, -1)}
                        className={`text-xs px-3 py-1.5 rounded-md font-semibold border cursor-pointer ${
                          rule.approved === -1
                            ? "bg-red-600 text-white border-red-600"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-red-50"
                        }`}
                      >
                        {rule.approved === -1 ? "✕ Rejected" : "Reject"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* =========================================================
              VIEW 4: REVIEW HISTORY & BENCHMARK ACCURACY SUITE
          ========================================================= */}
          {currentView === "history" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Review History & Reports</h1>
                  <p className="text-sm text-slate-500 mt-1">
                    Download past compliance audits or test Preflight accuracy against sample marketing content.
                  </p>
                </div>

                <button
                  onClick={handleRunBenchmark}
                  disabled={loading}
                  className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-4 py-2.5 rounded-lg cursor-pointer"
                >
                  {loading ? "Running Suite..." : "▶ Run Accuracy Benchmark Suite"}
                </button>
              </div>

              {/* History Table */}
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-bold">
                    <tr>
                      <th className="p-3.5">ID</th>
                      <th className="p-3.5">Content Title</th>
                      <th className="p-3.5">Score</th>
                      <th className="p-3.5">Status</th>
                      <th className="p-3.5">Date</th>
                      <th className="p-3.5 text-right">Download Report</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {historyList.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-50">
                        <td className="p-3.5 font-mono text-slate-400">#{item.id}</td>
                        <td className="p-3.5 font-bold text-slate-800">{item.content_title}</td>
                        <td className="p-3.5 font-bold">{item.overall_score}/100</td>
                        <td className="p-3.5">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                              item.status === "PASS"
                                ? "bg-emerald-100 text-emerald-800"
                                : item.status === "NEEDS_REVISION"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td className="p-3.5 text-slate-500">{item.created_at?.slice(0, 10)}</td>
                        <td className="p-3.5 text-right space-x-1.5">
                          <button
                            onClick={() => downloadReport(item.id, "md")}
                            className="text-blue-600 font-semibold hover:underline cursor-pointer"
                          >
                            .MD
                          </button>
                          <span className="text-slate-300">|</span>
                          <button
                            onClick={() => downloadReport(item.id, "html")}
                            className="text-blue-600 font-semibold hover:underline cursor-pointer"
                          >
                            .HTML
                          </button>
                          <span className="text-slate-300">|</span>
                          <button
                            onClick={() => downloadReport(item.id, "csv")}
                            className="text-blue-600 font-semibold hover:underline cursor-pointer"
                          >
                            .CSV
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Accuracy Benchmark Modal */}
      {showBenchmarkModal && benchmarkData && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl max-w-2xl w-full shadow-2xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 className="text-base font-bold text-slate-900">Compliance Detection Accuracy</h2>
              <button onClick={() => setShowBenchmarkModal(false)} className="text-slate-400 font-bold cursor-pointer">
                ✕
              </button>
            </div>

            <div className="grid grid-cols-4 gap-3">
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg text-center">
                <span className="text-[10px] uppercase font-bold text-slate-500">Accuracy</span>
                <p className="text-2xl font-bold text-blue-600 mt-0.5">{benchmarkData.accuracy}%</p>
              </div>
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg text-center">
                <span className="text-[10px] uppercase font-bold text-slate-500">Precision</span>
                <p className="text-2xl font-bold text-emerald-600 mt-0.5">{benchmarkData.precision_score}%</p>
              </div>
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg text-center">
                <span className="text-[10px] uppercase font-bold text-slate-500">Recall</span>
                <p className="text-2xl font-bold text-amber-600 mt-0.5">{benchmarkData.recall_score}%</p>
              </div>
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg text-center">
                <span className="text-[10px] uppercase font-bold text-slate-500">F1 Score</span>
                <p className="text-2xl font-bold text-purple-600 mt-0.5">{benchmarkData.f1_score}%</p>
              </div>
            </div>

            <div className="max-h-60 overflow-y-auto divide-y divide-slate-100 pr-1 text-xs">
              {benchmarkData.results?.map((res) => (
                <div key={res.sample_id} className="py-2.5 flex items-center justify-between">
                  <div>
                    <p className="font-bold text-slate-800">{res.title}</p>
                    <span className="text-[11px] text-slate-500">
                      Score: {res.overall_score}/100 • Predicted: {res.status}
                    </span>
                  </div>
                  <button
                    onClick={() => downloadReport(res.check_id, "md")}
                    className="text-blue-600 underline text-xs cursor-pointer"
                  >
                    Download Report
                  </button>
                </div>
              ))}
            </div>

            <button
              onClick={() => setShowBenchmarkModal(false)}
              className="w-full bg-slate-900 text-white py-2 rounded-lg text-xs font-semibold cursor-pointer"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}