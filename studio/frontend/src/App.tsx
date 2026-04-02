import { useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import * as preprocessApi from "./api/preprocess";
import * as projectsApi from "./api/projects";
import * as sfmApi from "./api/sfm";
import * as trainingApi from "./api/training";
import { PointCloudPreview } from "./components/PointCloudPreview";
import { useProjectWs } from "./hooks/useProjectWs";
import type { SfmBackendId, SfmBackendInfo } from "./types/sfm";

const steps = ["Upload", "Preprocess", "SfM", "Configure", "Train"] as const;

function WizardPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [project, setProject] = useState<projectsApi.Project | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fps, setFps] = useState(2);
  const [backends, setBackends] = useState<SfmBackendInfo[]>([]);
  const [sfmBackend, setSfmBackend] = useState<SfmBackendId>("colmap_incremental");
  const [sfmParams, setSfmParams] = useState<Record<string, unknown>>({
    max_num_features: 8192,
    matcher: "sequential",
    sequential_overlap: 10,
  });
  const [pc, setPc] = useState<{ positions: number[][]; colors: number[][] } | null>(null);
  const [sfmStats, setSfmStats] = useState({ ready: false, n_cameras: 0, n_points: 0 });
  const [cfgName, setCfgName] = useState("apps/colmap_3dgrt.yaml");
  const [experiment, setExperiment] = useState("studio_run");
  const [nIter, setNIter] = useState(30000);
  const { lines, lastStatus } = useProjectWs(projectId ?? null);

  const loadProject = useCallback(async () => {
    if (!projectId) return;
    const p = await projectsApi.listProjects();
    const found = p.find((x) => x.id === projectId);
    setProject(found || null);
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  useEffect(() => {
    sfmApi.getSfmBackends().then(setBackends).catch(() => setBackends([]));
  }, []);

  const refreshSfm = useCallback(async () => {
    if (!projectId) return;
    try {
      const st = await sfmApi.sfmStatus(projectId);
      setSfmStats(st);
      if (st.ready) {
        const cloud = await sfmApi.sfmPointcloud(projectId);
        setPc(cloud);
      }
    } catch {
      setPc(null);
    }
  }, [projectId]);

  useEffect(() => {
    const t = setInterval(refreshSfm, 3000);
    return () => clearInterval(t);
  }, [refreshSfm]);

  async function createProject() {
    const p = await projectsApi.createProject(name || "Untitled");
    nav(`/p/${p.id}`);
  }

  async function doUpload() {
    if (!projectId || !file) return;
    await preprocessApi.uploadVideo(projectId, file);
    await loadProject();
    setStep(1);
  }

  async function doPreprocess() {
    if (!projectId) return;
    await preprocessApi.startPreprocess(projectId, { fps, blur_threshold: 0 });
    setStep(2);
  }

  async function doSfm() {
    if (!projectId) return;
    await sfmApi.startSfm(projectId, sfmBackend, sfmParams);
    setStep(3);
  }

  async function doTrain() {
    if (!projectId) return;
    await trainingApi.startTraining(projectId, {
      config_name: cfgName,
      experiment_name: experiment,
      n_iterations: nIter,
    });
    setStep(4);
  }

  if (!projectId) {
    return (
      <div style={{ maxWidth: 520, margin: "48px auto", padding: 24 }}>
        <h1>3DGRUT Studio</h1>
        <p>New project</p>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Project name"
          style={{ width: "100%", padding: 8, marginBottom: 12 }}
        />
        <button type="button" onClick={() => void createProject()}>
          Create
        </button>
        <p style={{ marginTop: 24 }}>
          <Link to="/">Back to list</Link>
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside style={{ width: 220, borderRight: "1px solid #2a2f3d", padding: 16 }}>
        <Link to="/">Projects</Link>
        <h3 style={{ marginTop: 24 }}>{project?.name || "…"}</h3>
        <p style={{ fontSize: 12, opacity: 0.7 }}>{lastStatus}</p>
      </aside>
      <main style={{ flex: 1, padding: 24 }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
          {steps.map((s, i) => (
            <button
              key={s}
              type="button"
              onClick={() => setStep(i)}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid #2a2f3d",
                background: i === step ? "#2a3f6f" : "#1a1d26",
                color: "#e8e8ec",
              }}
            >
              {i + 1}. {s}
            </button>
          ))}
        </div>

        {step === 0 && (
          <section>
            <h2>Upload video</h2>
            <input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <p>
              <button type="button" disabled={!file} onClick={() => void doUpload()}>
                Upload & continue
              </button>
            </p>
          </section>
        )}

        {step === 1 && (
          <section>
            <h2>Preprocess</h2>
            <label>
              FPS{" "}
              <input
                type="number"
                value={fps}
                min={0.5}
                max={30}
                step={0.5}
                onChange={(e) => setFps(Number(e.target.value))}
              />
            </label>
            <p>
              <button type="button" onClick={() => void doPreprocess()}>
                Extract frames
              </button>
            </p>
          </section>
        )}

        {step === 2 && (
          <section>
            <h2>Structure from Motion</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
              {backends.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  disabled={!b.available}
                  onClick={() => setSfmBackend(b.id)}
                  style={{
                    textAlign: "left",
                    padding: 12,
                    borderRadius: 8,
                    border: `2px solid ${sfmBackend === b.id ? "#4a7ac9" : "#2a2f3d"}`,
                    background: b.available ? "#1a1d26" : "#0f1015",
                    color: b.available ? "#e8e8ec" : "#666",
                    opacity: b.available ? 1 : 0.55,
                  }}
                >
                  <strong>{b.display}</strong>
                  {b.requires_gpu && <div style={{ fontSize: 11 }}>GPU</div>}
                  {!b.available && b.install_hint && (
                    <div style={{ fontSize: 11, marginTop: 8 }}>{b.install_hint}</div>
                  )}
                </button>
              ))}
            </div>
            {sfmBackend === "colmap_incremental" && (
              <div style={{ marginTop: 16 }}>
                <label>
                  Matcher{" "}
                  <select
                    value={String(sfmParams.matcher || "sequential")}
                    onChange={(e) => setSfmParams((p) => ({ ...p, matcher: e.target.value }))}
                  >
                    <option value="sequential">sequential</option>
                    <option value="exhaustive">exhaustive</option>
                  </select>
                </label>
                <label style={{ marginLeft: 16 }}>
                  Max features{" "}
                  <input
                    type="number"
                    value={Number(sfmParams.max_num_features ?? 8192)}
                    onChange={(e) =>
                      setSfmParams((p) => ({ ...p, max_num_features: Number(e.target.value) }))
                    }
                  />
                </label>
              </div>
            )}
            {sfmBackend === "colmap_global" && (
              <div style={{ marginTop: 16 }}>
                <label>
                  Max features{" "}
                  <input
                    type="number"
                    value={Number(sfmParams.max_num_features ?? 8192)}
                    onChange={(e) =>
                      setSfmParams((p) => ({ ...p, max_num_features: Number(e.target.value) }))
                    }
                  />
                </label>
              </div>
            )}
            <p style={{ marginTop: 16 }}>
              <button type="button" onClick={() => void doSfm()}>
                Run SfM
              </button>
              <button type="button" style={{ marginLeft: 8 }} onClick={() => void refreshSfm()}>
                Refresh preview
              </button>
            </p>
            <p style={{ fontSize: 13 }}>
              Cameras: {sfmStats.n_cameras} · Points: {sfmStats.n_points} · Ready: {String(sfmStats.ready)}
            </p>
            <PointCloudPreview positions={pc?.positions ?? null} colors={pc?.colors ?? null} />
          </section>
        )}

        {step === 3 && (
          <section>
            <h2>Configure training</h2>
            <label style={{ display: "block", marginBottom: 8 }}>
              Hydra config name{" "}
              <input value={cfgName} onChange={(e) => setCfgName(e.target.value)} style={{ width: 360 }} />
            </label>
            <label style={{ display: "block", marginBottom: 8 }}>
              Experiment{" "}
              <input value={experiment} onChange={(e) => setExperiment(e.target.value)} />
            </label>
            <label style={{ display: "block", marginBottom: 8 }}>
              Iterations{" "}
              <input type="number" value={nIter} onChange={(e) => setNIter(Number(e.target.value))} />
            </label>
            <p>
              <button type="button" onClick={() => void doTrain()}>
                Launch training
              </button>
            </p>
          </section>
        )}

        {step === 4 && (
          <section>
            <h2>Training</h2>
            <pre
              style={{
                height: 360,
                overflow: "auto",
                background: "#0d0f14",
                padding: 12,
                fontSize: 11,
                borderRadius: 8,
              }}
            >
              {lines.join("\n")}
            </pre>
          </section>
        )}
      </main>
    </div>
  );
}

function Home() {
  const [projects, setProjects] = useState<projectsApi.Project[]>([]);
  const nav = useNavigate();
  useEffect(() => {
    projectsApi.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  return (
    <div style={{ maxWidth: 720, margin: "48px auto", padding: 24 }}>
      <h1>3DGRUT Studio</h1>
      <p>
        <button type="button" onClick={() => nav("/new")}>
          New project
        </button>
      </p>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {projects.map((p) => (
          <li key={p.id} style={{ marginBottom: 8 }}>
            <Link to={`/p/${p.id}`}>{p.name}</Link>
            <span style={{ opacity: 0.5, marginLeft: 8 }}>{p.status}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/new" element={<WizardPage />} />
      <Route path="/p/:projectId" element={<WizardPage />} />
    </Routes>
  );
}
