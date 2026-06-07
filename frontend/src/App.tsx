import React, { useState, useEffect } from 'react';

// API base URL pointing to FastAPI backend
const API_URL = 'http://localhost:8000/api';

interface MetricState {
  total_companies: number;
  qualified_companies: number;
  total_contacts: number;
  hubspot_synced_contacts: number;
  hubspot_synced_companies: number;
  average_ai_score: number;
}

interface Company {
  id: number;
  name: string;
  domain: string;
  industry: string | null;
  employee_count: number | null;
  revenue: string | null;
  ai_score: number | null;
  ai_explanation: string | null;
  discovery_source: string;
  status: string;
  hubspot_id: string | null;
  linkedin_url: string | null;
  created_at: string;
}

interface Contact {
  id: number;
  company_id: number;
  name: string;
  title: string | null;
  linkedin_url: string | null;
  email: string | null;
  phone: string | null;
  confidence_score: number;
  status: string;
  hubspot_id: string | null;
}

interface ICPConfig {
  id: number;
  industry: string;
  sub_vertical: string;
  geography: string;
  min_employee: number;
  max_employee: number;
  keywords: string | null;
  excluded_keywords: string | null;
  is_active: boolean;
}

interface LogSession {
  id: number;
  platform: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  logs: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [metrics, setMetrics] = useState<MetricState>({
    total_companies: 0,
    qualified_companies: 0,
    total_contacts: 0,
    hubspot_synced_contacts: 0,
    hubspot_synced_companies: 0,
    average_ai_score: 0,
  });
  const [companies, setCompanies] = useState<Company[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [icpConfigs, setIcpConfigs] = useState<ICPConfig[]>([]);
  const [logs, setLogs] = useState<LogSession[]>([]);
  const [activeJob, setActiveJob] = useState<any>(null);
  const [systemSettings, setSystemSettings] = useState<any>({});
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  
  // ICP form state
  const [icpForm, setIcpForm] = useState({
    industry: 'insurance',
    sub_vertical: 'MGA',
    geography: 'USA',
    min_employee: 50,
    max_employee: 1000,
    keywords: 'claims automation, underwriting technology, insurtech',
    excluded_keywords: 'life insurance, healthcare software',
  });

  const [targetName, setTargetName] = useState('');
  const [targetUrl, setTargetUrl] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  
  // Specific Targeting state variables
  const [targetSubTab, setTargetSubTab] = useState<'manual' | 'search' | 'bulk'>('manual');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [bulkText, setBulkText] = useState('');

  const handleTargetSubmit = async () => {
    if (!targetName && !targetUrl) {
      alert("Please enter a Company Name, Website Domain, or LinkedIn URL!");
      return;
    }
    try {
      const res = await fetch(`${API_URL}/companies/target`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          name: targetName || null, 
          website_or_domain: targetUrl || null 
        }),
      });
      if (res.ok) {
        setTargetName('');
        setTargetUrl('');
        alert("Target registered! Prospecting engine has queued this company.");
        fetchAllData();
        setActiveTab('dashboard');
      } else {
        const err = await res.json();
        alert("Error: " + err.detail);
      }
    } catch (e) {
      console.error("Targeting error:", e);
    }
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const res = await fetch(`${API_URL}/companies/search-external?query=${encodeURIComponent(searchQuery)}`);
      if (res.ok) {
        setSearchResults(await res.json());
      } else {
        alert("Error querying search index.");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelectSearchCompany = async (company: any) => {
    try {
      const res = await fetch(`${API_URL}/companies/target`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: company.name,
          website_or_domain: company.domain,
          linkedin_url: company.linkedin_url
        }),
      });
      if (res.ok) {
        alert(`Successfully added and targeted ${company.name}!`);
        setSearchQuery('');
        setSearchResults([]);
        fetchAllData();
        setActiveTab('dashboard');
      } else {
        const err = await res.json();
        alert("Error: " + err.detail);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleBulkSubmit = async () => {
    if (!bulkText.trim()) {
      alert("Please paste at least one target company website, LinkedIn URL, or name!");
      return;
    }
    
    const lines = bulkText.split('\n');
    const companiesList = lines.map(line => {
      const parts = line.split(',');
      if (parts.length >= 2) {
        return {
          name: parts[0].trim(),
          website_or_domain: parts[1].trim(),
          linkedin_url: parts[2] ? parts[2].trim() : null
        };
      } else {
        const item = line.trim();
        if (!item) return null;
        if (item.toLowerCase().includes('linkedin.com/company/')) {
          return { name: null, website_or_domain: null, linkedin_url: item };
        } else if (item.includes('.') && !item.includes(' ')) {
          return { name: null, website_or_domain: item, linkedin_url: null };
        } else {
          return { name: item, website_or_domain: null, linkedin_url: null };
        }
      }
    }).filter((c): c is any => c !== null && (!!c.website_or_domain || !!c.linkedin_url || !!c.name));

    if (companiesList.length === 0) {
      alert("Could not parse any valid company targets.");
      return;
    }

    try {
      const res = await fetch(`${API_URL}/companies/target-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ companies: companiesList }),
      });
      if (res.ok) {
        setBulkText('');
        alert(`Successfully registered ${companiesList.length} companies! Prospecting pipeline triggered.`);
        fetchAllData();
        setActiveTab('dashboard');
      } else {
        const err = await res.json();
        alert("Error importing companies: " + err.detail);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Initial Fetching
  const fetchAllData = async () => {
    try {
      // Fetch Metrics
      const resMetrics = await fetch(`${API_URL}/metrics`);
      if (resMetrics.ok) setMetrics(await resMetrics.json());

      // Fetch Companies
      const resCompanies = await fetch(`${API_URL}/companies`);
      if (resCompanies.ok) setCompanies(await resCompanies.json());

      // Fetch Contacts
      const resContacts = await fetch(`${API_URL}/contacts`);
      if (resContacts.ok) setContacts(await resContacts.json());

      // Fetch ICP Configurations
      const resIcp = await fetch(`${API_URL}/icp`);
      if (resIcp.ok) {
        const list = await resIcp.json();
        setIcpConfigs(list);
        // Set form with active config if it exists
        const active = list.find((i: ICPConfig) => i.is_active);
        if (active) {
          setIcpForm({
            industry: active.industry,
            sub_vertical: active.sub_vertical,
            geography: active.geography,
            min_employee: active.min_employee,
            max_employee: active.max_employee,
            keywords: active.keywords || '',
            excluded_keywords: active.excluded_keywords || '',
          });
        }
      }

      // Fetch Logs
      const resLogs = await fetch(`${API_URL}/logs`);
      if (resLogs.ok) setLogs(await resLogs.json());

      // Fetch dynamic settings
      const resSettings = await fetch(`${API_URL}/settings`);
      if (resSettings.ok) setSystemSettings(await resSettings.ok ? await resSettings.json() : {});

      // Fetch active job status
      const resJobs = await fetch(`${API_URL}/workflows/status`);
      if (resJobs.ok) {
        const jobs = await resJobs.json();
        const jobKeys = Object.keys(jobs);
        if (jobKeys.length > 0) {
          const currentJob = jobs[jobKeys[jobKeys.length - 1]];
          setActiveJob(currentJob);
          setIsRunning(currentJob.status === 'running');
        } else {
          setActiveJob(null);
          setIsRunning(false);
        }
      }
    } catch (e) {
      console.error("Error fetching data from API:", e);
    }
  };

  useEffect(() => {
    fetchAllData();
    // Poll updates every 4 seconds
    const interval = setInterval(fetchAllData, 4000);
    return () => clearInterval(interval);
  }, []);

  // Trigger prospecting run
  const handleTriggerRun = async () => {
    if (isRunning) return;
    setIsRunning(true);
    try {
      const res = await fetch(`${API_URL}/workflows/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        fetchAllData();
      } else {
        setIsRunning(false);
      }
    } catch (e) {
      console.error(e);
      setIsRunning(false);
    }
  };

  // Submit new ICP Config
  const handleIcpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_URL}/icp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...icpForm, is_active: true }),
      });
      if (res.ok) {
        alert("ICP Config updated successfully!");
        fetchAllData();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleForceSyncContact = async (contactId: number) => {
    try {
      const res = await fetch(`${API_URL}/contacts/${contactId}/sync`, {
        method: 'POST',
      });
      if (res.ok) {
        alert("Contact and company successfully synced to HubSpot! ML feedback recorded.");
        fetchAllData();
      } else {
        const err = await res.json();
        alert("Failed to sync: " + err.detail);
      }
    } catch (e) {
      console.error(e);
      alert("An error occurred during manual sync.");
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-icon">E</div>
          <div className="logo-text">EASY SDR</div>
        </div>
        <ul className="nav-links">
          <li 
            id="nav-tab-dashboard"
            className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </li>
          <li 
            id="nav-tab-icp"
            className={`nav-item ${activeTab === 'icp' ? 'active' : ''}`}
            onClick={() => setActiveTab('icp')}
          >
            ICP Configuration
          </li>
          <li 
            id="nav-tab-companies"
            className={`nav-item ${activeTab === 'companies' ? 'active' : ''}`}
            onClick={() => setActiveTab('companies')}
          >
            Target Accounts
          </li>
          <li 
            id="nav-tab-contacts"
            className={`nav-item ${activeTab === 'contacts' ? 'active' : ''}`}
            onClick={() => setActiveTab('contacts')}
          >
            Enriched Contacts
          </li>
          <li 
            id="nav-tab-logs"
            className={`nav-item ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            System Logs
          </li>
          <li 
            id="nav-tab-settings"
            className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            System Settings
          </li>
        </ul>
      </aside>

      {/* Main Viewport */}
      <main className="main-viewport">
        {/* Header */}
        <header className="app-header">
          <div className="header-title">
            <h1>
              {activeTab === 'dashboard' && 'Dashboard Overview'}
              {activeTab === 'icp' && 'Targeting & ICP Rules'}
              {activeTab === 'companies' && 'Target Companies'}
              {activeTab === 'contacts' && 'Enriched Contacts'}
              {activeTab === 'logs' && 'Real-time System Logs'}
              {activeTab === 'settings' && 'System Configurations & API Keys'}
            </h1>
          </div>
          <div className="header-actions">
            <button 
              id="btn-run-pipeline"
              className={`btn ${isRunning ? 'btn-running' : ''}`}
              onClick={handleTriggerRun}
              disabled={isRunning}
            >
              {isRunning ? (
                <>
                  <span className="spin">⏳</span> Running Prospector...
                </>
              ) : (
                <>
                  🚀 Run Prospecting Pipeline
                </>
              )}
            </button>
          </div>
        </header>

        {/* View Content */}
        <div className="view-container">
          {/* Top Metrics Summary (Shown in Dashboard, Accounts, and Contacts tabs) */}
          {activeTab !== 'logs' && activeTab !== 'icp' && (
            <section className="metrics-row">
              <div className="metric-card">
                <span className="metric-label">Discovered Companies</span>
                <span className="metric-value">{metrics.total_companies}</span>
                <span className="metric-trend trend-up">↑ 100% automated</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">AI Qualified Fit</span>
                <span className="metric-value">{metrics.qualified_companies}</span>
                <span className="metric-trend trend-up">↑ target score ≥70</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Enriched Contacts</span>
                <span className="metric-value">{metrics.total_contacts}</span>
                <span className="metric-trend trend-up">↑ scored & validated</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">CRM HubSpot Synced</span>
                <span className="metric-value">{metrics.hubspot_synced_contacts}</span>
                <span className="metric-trend trend-up">↑ sync success</span>
              </div>
            </section>
          )}

          {/* TAB 1: DASHBOARD */}
          {activeTab === 'dashboard' && (
            <>
              {/* Pipeline Tracker */}
              <div className="widget">
                <div className="widget-title">
                  <span>SDR Automation Pipeline Status</span>
                  {isRunning && <span className="badge badge-success">Pipeline Active</span>}
                </div>
                <div className="pipeline-track">
                  <div className={`pipeline-node ${isRunning || metrics.total_companies > 0 ? 'success' : ''}`}>
                    <div className="node-icon">🔍</div>
                    <strong>Account Discovery</strong>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Apollo Search API</span>
                  </div>
                  <div className={`pipeline-node ${isRunning && activeJob?.stage?.includes('qualifying') ? 'active' : metrics.qualified_companies > 0 ? 'success' : ''}`}>
                    <div className="node-icon">🧠</div>
                    <strong>AI Qualification</strong>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Kimi AI scoring</span>
                  </div>
                  <div className={`pipeline-node ${isRunning && activeJob?.stage?.includes('extracting') ? 'active' : metrics.total_contacts > 0 ? 'success' : ''}`}>
                    <div className="node-icon">👤</div>
                    <strong>Contact Enrichment</strong>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Playwright / MX Check</span>
                  </div>
                  <div className={`pipeline-node ${isRunning && activeJob?.stage?.includes('syncing') ? 'active' : metrics.hubspot_synced_contacts > 0 ? 'success' : ''}`}>
                    <div className="node-icon">🔌</div>
                    <strong>CRM HubSpot Sync</strong>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Auto deduplication</span>
                  </div>
                </div>
              </div>

              {/* Grid layout for recent activity */}
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
                {/* Recent Qualified Accounts */}
                <div className="widget">
                  <div className="widget-title">Recent Qualified Target Companies</div>
                  <div className="table-wrapper">
                    <table className="lead-table">
                      <thead>
                        <tr>
                          <th>Company Name</th>
                          <th>Domain</th>
                          <th>Employees</th>
                          <th>AI Score</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {companies.slice(0, 5).map((co) => (
                          <tr key={co.id}>
                            <td style={{ fontWeight: 600 }}>{co.name}</td>
                            <td>{co.domain}</td>
                            <td>{co.employee_count || 'N/A'}</td>
                            <td>
                              <span style={{
                                color: (co.ai_score || 0) >= 80 ? '#10b981' : '#f59e0b',
                                fontWeight: 700
                              }}>
                                {co.ai_score || 'N/A'}/100
                              </span>
                            </td>
                            <td>
                              <span className={`badge ${
                                co.status === 'synced' ? 'badge-success' : 
                                co.status === 'qualified' ? 'badge-primary' : 
                                co.status === 'disqualified' ? 'badge-danger' : 'badge-warning'
                              }`}>
                                {co.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                        {companies.length === 0 && (
                          <tr>
                            <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                              No companies discovered yet. Trigger the pipeline to start discovery!
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* System Efficiency Metrics */}
                <div className="widget">
                  <div className="widget-title">Conversion Performance</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.9rem' }}>
                        <span>Target Relevance Fit Rate</span>
                        <strong>{metrics.total_companies > 0 ? Math.round((metrics.qualified_companies / metrics.total_companies) * 100) : 0}%</strong>
                      </div>
                      <div style={{ height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          background: 'linear-gradient(90deg, var(--primary), var(--secondary))',
                          width: `${metrics.total_companies > 0 ? (metrics.qualified_companies / metrics.total_companies) * 100 : 0}%`
                        }} />
                      </div>
                    </div>

                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.9rem' }}>
                        <span>CRM Sync Match Success</span>
                        <strong>{metrics.total_contacts > 0 ? Math.round((metrics.hubspot_synced_contacts / metrics.total_contacts) * 100) : 0}%</strong>
                      </div>
                      <div style={{ height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%',
                          background: 'linear-gradient(90deg, var(--primary), var(--success))',
                          width: `${metrics.total_contacts > 0 ? (metrics.hubspot_synced_contacts / metrics.total_contacts) * 100 : 0}%`
                        }} />
                      </div>
                    </div>

                    <div style={{ padding: '16px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      <strong>Active Target Persona Focus:</strong>
                      <ul style={{ paddingLeft: '20px', marginTop: '8px' }}>
                        <li>Claims & Operations CXOs</li>
                        <li>Head of Transformation</li>
                        <li>Director of Underwriting</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* TAB 2: ICP TARGETING CONFIG */}
          {activeTab === 'icp' && (
            <div className="widget">
              <div className="widget-title">
                <span>Configure Ideal Customer Profile Rules</span>
                {icpConfigs.length > 0 && (
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 'normal' }}>
                    Active Target: {icpConfigs.find(i => i.is_active)?.industry} ({icpConfigs.find(i => i.is_active)?.sub_vertical})
                  </span>
                )}
              </div>
              <form id="form-icp-config" onSubmit={handleIcpSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <div className="form-grid">
                  <div className="form-group">
                    <label>Target Industry</label>
                    <input 
                      id="input-icp-industry"
                      type="text" 
                      className="form-input" 
                      value={icpForm.industry}
                      onChange={(e) => setIcpForm({ ...icpForm, industry: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Sub-vertical Profile</label>
                    <input 
                      id="input-icp-subvertical"
                      type="text" 
                      className="form-input"
                      value={icpForm.sub_vertical}
                      onChange={(e) => setIcpForm({ ...icpForm, sub_vertical: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Target Geography</label>
                    <input 
                      id="input-icp-geography"
                      type="text" 
                      className="form-input"
                      value={icpForm.geography}
                      onChange={(e) => setIcpForm({ ...icpForm, geography: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-grid">
                  <div className="form-group">
                    <label>Min Employees</label>
                    <input 
                      id="input-icp-min-employees"
                      type="number" 
                      className="form-input"
                      value={icpForm.min_employee}
                      onChange={(e) => setIcpForm({ ...icpForm, min_employee: parseInt(e.target.value) || 0 })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Max Employees</label>
                    <input 
                      id="input-icp-max-employees"
                      type="number" 
                      className="form-input"
                      value={icpForm.max_employee}
                      onChange={(e) => setIcpForm({ ...icpForm, max_employee: parseInt(e.target.value) || 0 })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Company Keywords (comma-separated)</label>
                  <textarea 
                    id="input-icp-keywords"
                    className="form-input" 
                    style={{ minHeight: '80px', resize: 'vertical' }}
                    value={icpForm.keywords}
                    onChange={(e) => setIcpForm({ ...icpForm, keywords: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Excluded Keywords (comma-separated)</label>
                  <textarea 
                    id="input-icp-excluded-keywords"
                    className="form-input" 
                    style={{ minHeight: '80px', resize: 'vertical' }}
                    value={icpForm.excluded_keywords}
                    onChange={(e) => setIcpForm({ ...icpForm, excluded_keywords: e.target.value })}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button id="btn-save-icp" type="submit" className="btn">
                    💾 Save Active ICP Configuration
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* TAB 3: TARGET ACCOUNTS */}
          {activeTab === 'companies' && (
            <div className="widget">
              <div className="widget-title">Prospect Accounts Discovered & Qualified</div>
              
              {/* Selector Tabs for Targeting Options */}
              <div className="widget-tabs">
                <button 
                  id="tab-target-manual"
                  className={`widget-tab-button ${targetSubTab === 'manual' ? 'active' : ''}`}
                  onClick={() => setTargetSubTab('manual')}
                >
                  🎯 Target Single Account
                </button>
                <button 
                  id="tab-target-search"
                  className={`widget-tab-button ${targetSubTab === 'search' ? 'active' : ''}`}
                  onClick={() => setTargetSubTab('search')}
                >
                  🔍 Global Company Search
                </button>
                <button 
                  id="tab-target-bulk"
                  className={`widget-tab-button ${targetSubTab === 'bulk' ? 'active' : ''}`}
                  onClick={() => setTargetSubTab('bulk')}
                >
                  📁 Bulk Import List
                </button>
              </div>

              {/* Sub-tab 1: Manual Direct Targeting */}
              {targetSubTab === 'manual' && (
                <div style={{ 
                  display: 'flex', 
                  gap: '16px', 
                  background: 'rgba(255,255,255,0.01)', 
                  padding: '20px', 
                  borderRadius: '10px', 
                  border: '1px solid var(--border-color)', 
                  alignItems: 'flex-end', 
                  flexWrap: 'wrap',
                  marginBottom: '10px'
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: '200px' }}>
                    <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Company Name (Optional)</label>
                    <input 
                      id="input-manual-company-name"
                      type="text" 
                      className="form-input" 
                      placeholder="e.g. ClaimsGuard MGA"
                      value={targetName}
                      onChange={(e) => setTargetName(e.target.value)}
                    />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1.5, minWidth: '250px' }}>
                    <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>Website URL / Domain / LinkedIn Link</label>
                    <input 
                      id="input-manual-company-url"
                      type="text" 
                      className="form-input" 
                      placeholder="e.g. claimsguard.com OR linkedin.com/company/claimsguard"
                      value={targetUrl}
                      onChange={(e) => setTargetUrl(e.target.value)}
                    />
                  </div>
                  <button 
                    id="btn-manual-target-submit"
                    className="btn" 
                    style={{ height: '44px' }}
                    onClick={handleTargetSubmit}
                  >
                    🎯 Target Account
                  </button>
                </div>
              )}

              {/* Sub-tab 2: Global Search */}
              {targetSubTab === 'search' && (
                <div style={{ marginBottom: '10px' }}>
                  <form id="form-global-search" onSubmit={handleSearchSubmit} style={{ 
                    display: 'flex', 
                    gap: '12px', 
                    background: 'rgba(255,255,255,0.01)', 
                    padding: '20px', 
                    borderRadius: '10px', 
                    border: '1px solid var(--border-color)'
                  }}>
                    <input 
                      id="input-global-search-query"
                      type="text" 
                      className="form-input" 
                      style={{ flex: 1 }}
                      placeholder="Search companies by name or keyword tags (e.g. Claims MGA, SureWay)..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    <button id="btn-global-search-submit" type="submit" className="btn" disabled={isSearching}>
                      {isSearching ? "Searching..." : "🔍 Search external index"}
                    </button>
                  </form>

                  {searchResults.length > 0 && (
                    <div className="search-results-list">
                      {searchResults.map((org, index) => (
                        <div className="search-result-card" key={index}>
                          <div className="search-result-info">
                            <span className="search-result-name">{org.name}</span>
                            <div className="search-result-meta">
                              <span>🌐 {org.domain}</span>
                              {org.linkedin_url && <span>🔗 LinkedIn Connected</span>}
                              <span>👥 {org.employee_count} employees</span>
                              <span>💼 {org.industry}</span>
                            </div>
                          </div>
                          <button 
                            className="btn btn-secondary" 
                            onClick={() => handleSelectSearchCompany(org)}
                          >
                            🎯 Prospect Account
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Sub-tab 3: Bulk Import */}
              {targetSubTab === 'bulk' && (
                <div style={{ 
                  display: 'flex', 
                  flexDirection: 'column',
                  gap: '16px', 
                  background: 'rgba(255,255,255,0.01)', 
                  padding: '20px', 
                  borderRadius: '10px', 
                  border: '1px solid var(--border-color)',
                  marginBottom: '10px'
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                      Paste Company List (One website link, LinkedIn page, or name per line. Optional: Name, Website, LinkedIn comma-separated)
                    </label>
                    <textarea 
                      id="input-bulk-import-textarea"
                      className="form-input bulk-textarea" 
                      placeholder="e.g.&#10;claimsguard.com&#10;https://www.linkedin.com/company/sureway-underwriters&#10;Insurtech Labs, insurtechlabs.co"
                      value={bulkText}
                      onChange={(e) => setBulkText(e.target.value)}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button 
                      id="btn-bulk-import-submit"
                      className="btn" 
                      onClick={handleBulkSubmit}
                    >
                      🚀 Import & Prospect List
                    </button>
                  </div>
                </div>
              )}

              {/* Targets Table */}
              <div className="table-wrapper">
                <table className="lead-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Domain</th>
                      <th>LinkedIn Profile</th>
                      <th>Employees</th>
                      <th>Revenue (Est)</th>
                      <th>Discovery Source</th>
                      <th>AI Fit Score</th>
                      <th>AI Fit Explanation</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map((co) => (
                      <tr key={co.id}>
                        <td style={{ fontWeight: 600 }}>{co.name}</td>
                        <td>
                          <a href={`https://${co.domain}`} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                            {co.domain}
                          </a>
                        </td>
                        <td>
                          {co.linkedin_url ? (
                            <a href={co.linkedin_url} target="_blank" rel="noreferrer" style={{ color: 'var(--secondary)', textDecoration: 'none' }}>
                              LinkedIn Page
                            </a>
                          ) : (
                            <span style={{ color: 'var(--text-dim)' }}>N/A</span>
                          )}
                        </td>
                        <td>{co.employee_count || 'N/A'}</td>
                        <td>{co.revenue || 'N/A'}</td>
                        <td>{co.discovery_source}</td>
                        <td>
                          <strong style={{ color: (co.ai_score || 0) >= 80 ? '#10b981' : '#f59e0b' }}>
                            {co.ai_score || 'N/A'}/100
                          </strong>
                        </td>
                        <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: '280px' }}>
                          {co.ai_explanation || 'Awaiting evaluation.'}
                        </td>
                        <td>
                          <span className={`badge ${
                            co.status === 'synced' ? 'badge-success' : 
                            co.status === 'qualified' ? 'badge-primary' : 
                            co.status === 'disqualified' ? 'badge-danger' : 'badge-warning'
                          }`}>
                            {co.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {companies.length === 0 && (
                      <tr>
                        <td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '30px' }}>
                          No accounts discovered yet. Run the prospecting pipeline to search.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 4: ENRICHED CONTACTS */}
          {activeTab === 'contacts' && (
            <div className="widget">
              <div className="widget-title">Decision Maker Leads Details</div>
              <div className="table-wrapper">
                <table className="lead-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Title</th>
                      <th>Company</th>
                      <th>Email</th>
                      <th>Phone</th>
                      <th>LinkedIn Url</th>
                      <th>Confidence Score</th>
                      <th>HubSpot Id</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contacts.map((c) => {
                      const co = companies.find(org => org.id === c.company_id);
                      return (
                        <tr key={c.id}>
                          <td style={{ fontWeight: 600 }}>{c.name}</td>
                          <td>{c.title || 'N/A'}</td>
                          <td>{co ? co.name : 'Unknown'}</td>
                          <td>{c.email || 'N/A'}</td>
                          <td>{c.phone || 'N/A'}</td>
                          <td>
                            {c.linkedin_url ? (
                              <a href={c.linkedin_url} target="_blank" rel="noreferrer" style={{ color: 'var(--secondary)', textDecoration: 'none' }}>
                                View Profile
                              </a>
                            ) : 'N/A'}
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ fontWeight: 700 }}>{c.confidence_score}%</span>
                              <div style={{ width: '40px', height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
                                <div style={{
                                  height: '100%',
                                  background: c.confidence_score >= 80 ? 'var(--success)' : 'var(--warning)',
                                  width: `${c.confidence_score}%`
                                }} />
                              </div>
                            </div>
                          </td>
                          <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{c.hubspot_id || 'Not Synced'}</td>
                          <td>
                            <span className={`badge ${
                              c.status === 'synced' ? 'badge-success' : 
                              c.status === 'enriched' ? 'badge-primary' : 
                              c.status === 'ignored' ? 'badge-danger' : 'badge-warning'
                            }`}>
                              {c.status}
                            </span>
                          </td>
                          <td>
                            {c.status !== 'synced' ? (
                              <button 
                                id={`btn-sync-contact-${c.id}`}
                                className="btn btn-secondary" 
                                style={{ padding: '6px 12px', fontSize: '0.75rem', display: 'inline-flex', gap: '4px' }}
                                onClick={() => handleForceSyncContact(c.id)}
                              >
                                ⚡ Push to CRM
                              </button>
                            ) : (
                              <span style={{ color: 'var(--success)', fontSize: '0.8rem', fontWeight: 600 }}>✓ Synced</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {contacts.length === 0 && (
                      <tr>
                        <td colSpan={10} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '30px' }}>
                          No contacts enriched yet. Discovered accounts must be qualified and decision-makers extracted.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 5: SYSTEM SCRAPING LOGS */}
          {activeTab === 'logs' && (
            <div className="widget">
              <div className="widget-title">Live Pipeline Activity Log Console</div>
              <div className="console-logs">
                {logs.length > 0 ? (
                  logs[0].logs.split('\n').map((line, idx) => (
                    <div className="log-entry" key={idx}>
                      <span className="log-time">[{new Date(logs[0].started_at).toLocaleTimeString()}]</span>
                      {line}
                    </div>
                  ))
                ) : (
                  <div className="log-entry">No active jobs run log found. Trigger the pipeline to view activity logs.</div>
                )}
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Polling active scraper status. Playwright crawler is configured in simulated browser mode for target verification.
              </div>
            </div>
          )}

          {/* TAB 6: SYSTEM CONFIGURATION SETTINGS */}
          {activeTab === 'settings' && (
            <div className="widget">
              <div className="widget-title">Configure System Settings & API Integrations</div>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '16px' }}>
                Manage API keys, endpoints, and credentials for autonomous prospecting channels. Empty values or keys set to "mock" will fall back to simulated test behavior.
              </p>
              
              <div className="settings-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px', marginBottom: '24px' }}>
                {/* Card 1: Kimi Moonshot AI */}
                <div className="settings-card" style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: '12px' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'white', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>🧠 Moonshot Kimi AI (Decision Engine)</span>
                    <span className={`badge ${systemSettings.KIMI_API_KEY?.is_configured ? 'badge-success' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                      {systemSettings.KIMI_API_KEY?.is_configured ? 'Active AI Model' : 'Mock Mode'}
                    </span>
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div className="form-group">
                      <label>Kimi Moonshot API Key</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="your_kimi_moonshot_api_key"
                        value={systemSettings.KIMI_API_KEY?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          KIMI_API_KEY: { ...systemSettings.KIMI_API_KEY, value: e.target.value }
                        })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Kimi API Base URL</label>
                      <input 
                        type="text" 
                        className="form-input" 
                        placeholder="https://api.moonshot.cn/v1"
                        value={systemSettings.KIMI_BASE_URL?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          KIMI_BASE_URL: { ...systemSettings.KIMI_BASE_URL, value: e.target.value }
                        })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Kimi AI Model Name</label>
                      <input 
                        type="text" 
                        className="form-input" 
                        placeholder="moonshot-v1-8k"
                        value={systemSettings.KIMI_MODEL?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          KIMI_MODEL: { ...systemSettings.KIMI_MODEL, value: e.target.value }
                        })}
                      />
                    </div>
                  </div>
                </div>

                {/* Card 2: Apollo & Datanyze */}
                <div className="settings-card" style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: '12px' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'white', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>🔍 Prospect Discovery & Enrichment</span>
                    <span className={`badge ${(systemSettings.APOLLO_API_KEY?.is_configured || systemSettings.DATANYZE_API_KEY?.is_configured) ? 'badge-success' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                      {systemSettings.APOLLO_API_KEY?.is_configured ? 'API Live' : 'Mock Mode'}
                    </span>
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div className="form-group">
                      <label>Apollo API Key (Company Search)</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="your_apollo_api_key_here"
                        value={systemSettings.APOLLO_API_KEY?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          APOLLO_API_KEY: { ...systemSettings.APOLLO_API_KEY, value: e.target.value }
                        })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Datanyze API Key (Contact Enrichment)</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="your_datanyze_api_key_here"
                        value={systemSettings.DATANYZE_API_KEY?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          DATANYZE_API_KEY: { ...systemSettings.DATANYZE_API_KEY, value: e.target.value }
                        })}
                      />
                    </div>
                    <div className="form-group">
                      <label>ZoomInfo Token (Optional)</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="your_zoominfo_token_here"
                        value={systemSettings.ZOOMINFO_API_KEY?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          ZOOMINFO_API_KEY: { ...systemSettings.ZOOMINFO_API_KEY, value: e.target.value }
                        })}
                      />
                    </div>
                  </div>
                </div>

                {/* Card 3: HubSpot & LinkedIn */}
                <div className="settings-card" style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: '12px' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'white', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>🔌 CRM Sync & Playwright Crawler</span>
                    <span className={`badge ${systemSettings.HUBSPOT_ACCESS_TOKEN?.is_configured ? 'badge-success' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                      {systemSettings.HUBSPOT_ACCESS_TOKEN?.is_configured ? 'CRM Active' : 'Mock Mode'}
                    </span>
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div className="form-group">
                      <label>HubSpot Developer Access Token</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="pat-na-xxxxxxxxxxxxxxxxxxxxxxxx"
                        value={systemSettings.HUBSPOT_ACCESS_TOKEN?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          HUBSPOT_ACCESS_TOKEN: { ...systemSettings.HUBSPOT_ACCESS_TOKEN, value: e.target.value }
                        })}
                      />
                    </div>
                    <div className="form-group">
                      <label>LinkedIn Crawler Account Username</label>
                      <input 
                        type="text" 
                        className="form-input" 
                        placeholder="user@domain.com"
                        value={systemSettings.LINKEDIN_USERNAME?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          LINKEDIN_USERNAME: { ...systemSettings.LINKEDIN_USERNAME, value: e.target.value }
                        })}
                      />
                    </div>
                    <div className="form-group">
                      <label>LinkedIn Account Password</label>
                      <input 
                        type="password" 
                        className="form-input" 
                        placeholder="linkedin_password"
                        value={systemSettings.LINKEDIN_PASSWORD?.value || ''}
                        onChange={(e) => setSystemSettings({
                          ...systemSettings,
                          LINKEDIN_PASSWORD: { ...systemSettings.LINKEDIN_PASSWORD, value: e.target.value }
                        })}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Cookies Area */}
              <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: '12px', marginBottom: '24px' }}>
                <div className="form-group">
                  <label style={{ fontSize: '1rem', fontWeight: 600, color: 'white', marginBottom: '8px', display: 'block' }}>
                    🍪 LinkedIn Playwright Session Cookies (JSON Block)
                  </label>
                  <textarea 
                    className="form-input" 
                    style={{ minHeight: '80px', fontFamily: 'monospace', fontSize: '0.8rem' }}
                    placeholder='[{"name": "li_at", "value": "AQED...", "domain": ".linkedin.com"}]'
                    value={systemSettings.LINKEDIN_COOKIES_JSON?.value || ''}
                    onChange={(e) => setSystemSettings({
                      ...systemSettings,
                      LINKEDIN_COOKIES_JSON: { ...systemSettings.LINKEDIN_COOKIES_JSON, value: e.target.value }
                    })}
                  />
                  <small style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '6px', display: 'block' }}>
                    Paste a JSON cookies block extracted from your browser to bypass LinkedIn bot detection.
                  </small>
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button 
                  className="btn btn-secondary" 
                  onClick={() => fetchAllData()}
                  disabled={isSavingSettings}
                >
                  🔄 Refresh Configurations
                </button>
                <button 
                  className="btn" 
                  onClick={async () => {
                    setIsSavingSettings(true);
                    try {
                      const payload: any = {};
                      Object.keys(systemSettings).forEach(key => {
                        payload[key] = systemSettings[key].value;
                      });
                      const res = await fetch(`${API_URL}/settings`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                      });
                      if (res.ok) {
                        alert("API configurations and credentials saved successfully!");
                        fetchAllData();
                      } else {
                        const err = await res.json();
                        alert("Error saving settings: " + err.detail);
                      }
                    } catch (e) {
                      console.error("Save error:", e);
                      alert("Failed to save credentials.");
                    } finally {
                      setIsSavingSettings(false);
                    }
                  }}
                  disabled={isSavingSettings}
                >
                  {isSavingSettings ? 'Saving Settings...' : '💾 Save Systems Integration'}
                </button>
              </div>
            </div>
          )}
        </div>
        <footer className="app-footer" style={{
          padding: '24px 40px',
          borderTop: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          color: 'var(--text-dim)',
          fontSize: '0.8rem',
          background: 'rgba(8, 10, 22, 0.2)',
          backdropFilter: 'var(--panel-blur)'
        }}>
          <div>
            &copy; 2026 <strong>EasySDR</strong>. Designed by <strong>Faiz</strong>. All rights reserved.
          </div>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
            <span>v1.0.0 (Production Ready)</span>
            <span>&bull;</span>
            <span style={{ color: 'var(--success)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }}></span>
              All systems operational
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
