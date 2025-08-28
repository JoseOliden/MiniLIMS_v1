# Mini LIMS con Streamlit — app.py
# Autor: ChatGPT (GPT-5 Thinking)
# Fecha: 2025-08-28
# Objetivo: Aplicación de escritorio simple tipo LIMS para laboratorios pequeños (ISO/IEC 17025)
# Ejecución:
#   1) Instalar dependencias: pip install streamlit pandas sqlite3-bro json5 python-dateutil
#      (sqlite3 viene con Python estándar)
#   2) Ejecutar: streamlit run app.py
#   3) El archivo de base de datos se crea en ./lims.db

import sqlite3
import json
from datetime import datetime, date
from dateutil import tz
from typing import Optional, Dict, Any, List

import pandas as pd
import streamlit as st

# =============================
# Configuración de la App
# =============================
st.set_page_config(
    page_title="Mini LIMS",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOCAL_TZ = tz.gettz("America/Lima")
DB_PATH = "lims.db"

# =============================
# Utilitarios
# =============================

def now_ts() -> str:
    return datetime.now(tz=LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S%z")


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = dict_factory
    return conn


def run_query(sql: str, params: tuple = ()):  # returns list[dict]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.commit()
    conn.close()
    return rows


def run_execute(sql: str, params: tuple = ()):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


# =============================
# Inicialización DB (si no existe)
# =============================
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL DEFAULT 'analyst',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS samples (
        id TEXT PRIMARY KEY,
        client TEXT,
        project TEXT,
        matrix TEXT,
        description TEXT,
        received_at TEXT,
        due_at TEXT,
        status TEXT NOT NULL DEFAULT 'registrado',
        priority TEXT NOT NULL DEFAULT 'normal',
        location TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_id TEXT NOT NULL,
        test_name TEXT NOT NULL,
        method TEXT,
        unit TEXT,
        status TEXT NOT NULL DEFAULT 'pendiente',
        assigned_to TEXT,
        due_at TEXT,
        FOREIGN KEY(sample_id) REFERENCES samples(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_id INTEGER NOT NULL,
        analyte TEXT NOT NULL,
        value REAL,
        unit TEXT,
        uncertainty REAL,
        notes TEXT,
        measured_at TEXT,
        FOREIGN KEY(test_id) REFERENCES tests(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_id TEXT NOT NULL,
        label TEXT,
        url TEXT NOT NULL,
        added_by TEXT,
        added_at TEXT NOT NULL,
        FOREIGN KEY(sample_id) REFERENCES samples(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS coc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_id TEXT NOT NULL,
        event TEXT NOT NULL,
        by_user TEXT,
        at_time TEXT NOT NULL,
        notes TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        by_user TEXT,
        at_time TEXT NOT NULL,
        details TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS qc_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        instrument TEXT,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'abierto',
        at_time TEXT NOT NULL,
        by_user TEXT
    );
    """,
]


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    for stmt in SCHEMA:
        cur.executescript(stmt)
    # Valores iniciales
    if not run_query("SELECT value FROM meta WHERE key='seq_ano'"):
        run_execute("INSERT INTO meta(key, value) VALUES(?, ?)", ("seq_ano", str(datetime.now().year)))
    if not run_query("SELECT value FROM meta WHERE key='seq_num'"):
        run_execute("INSERT INTO meta(key, value) VALUES(?, ?)", ("seq_num", "0"))
    if not run_query("SELECT * FROM users WHERE username=?", ("admin",)):
        run_execute(
            "INSERT INTO users(username, role, active, created_at) VALUES(?,?,?,?)",
            ("admin", "admin", 1, now_ts()),
        )
    conn.close()


init_db()

# =============================
# Auditoría
# =============================

def audit(entity: str, entity_id: str, action: str, by_user: str, details: Optional[Dict[str, Any]] = None):
    run_execute(
        "INSERT INTO audit(entity, entity_id, action, by_user, at_time, details) VALUES(?,?,?,?,?,?)",
        (entity, entity_id, action, by_user, now_ts(), json.dumps(details or {})),
    )


# =============================
# Generador de IDs de muestra
# =============================

def next_sample_id() -> str:
    year = str(datetime.now().year)
    seq_year = run_query("SELECT value FROM meta WHERE key='seq_ano'")
    seq_num = int(run_query("SELECT value FROM meta WHERE key='seq_num'")[0]["value"])
    if not seq_year or seq_year[0]["value"] != year:
        run_execute("UPDATE meta SET value=? WHERE key='seq_ano'", (year,))
        seq_num = 0
    seq_num += 1
    run_execute("UPDATE meta SET value=? WHERE key='seq_num'", (str(seq_num),))
    return f"S-{year}-{seq_num:04d}"


# =============================
# Sidebar: sesión de usuario simple
# =============================
with st.sidebar:
    st.title("🧪 Mini LIMS")
    st.caption("ISO/IEC 17025 — laboratorio pequeño")

    if "user" not in st.session_state:
        st.session_state.user = "admin"

    user = st.text_input("Usuario activo", st.session_state.user, help="Solo para trazabilidad. (No hay contraseña en esta versión)")
    st.session_state.user = user.strip() or "anon"

    st.markdown("---")
    page = st.radio(
        "Navegación",
        [
            "📊 Dashboard",
            "📝 Registro de muestras",
            "📦 Muestras",
            "🧫 Ensayos & Resultados",
            "📎 Adjuntos / Links",
            "✅ Control de Calidad",
            "📈 Reportes & Exportación",
            "⚙️ Administración",
            "🧾 Auditoría",
        ],
        index=0,
    )

# =============================
# Páginas
# =============================

# ------ Dashboard ------
if page == "📊 Dashboard":
    st.header("📊 Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    total = run_query("SELECT COUNT(*) AS c FROM samples")[0]["c"]
    abiertos = run_query("SELECT COUNT(*) AS c FROM samples WHERE status NOT IN ('cerrado','cancelado')")[0]["c"]
    pendientes = run_query("SELECT COUNT(*) AS c FROM tests WHERE status='pendiente'")[0]["c"]
    qc_abiertos = run_query("SELECT COUNT(*) AS c FROM qc_events WHERE status='abierto'")[0]["c"]
    c1.metric("Muestras totales", total)
    c2.metric("Muestras abiertas", abiertos)
    c3.metric("Ensayos pendientes", pendientes)
    c4.metric("Eventos QC abiertos", qc_abiertos)

    st.subheader("⏰ Vencimientos próximos (7 días)")
    df_due = pd.DataFrame(run_query("""
        SELECT s.id AS sample_id, s.client, s.project, s.due_at, s.status
        FROM samples s
        WHERE s.due_at IS NOT NULL AND DATE(s.due_at) <= DATE('now','+7 day') AND s.status NOT IN ('cerrado','cancelado')
        ORDER BY s.due_at ASC
    """))
    if df_due.empty:
        st.info("Sin vencimientos próximos.")
    else:
        st.dataframe(df_due, use_container_width=True)

# ------ Registro de muestras ------
elif page == "📝 Registro de muestras":
    st.header("📝 Registro de muestras")

    with st.form("frm_sample"):
        c1, c2, c3 = st.columns(3)
        client = c1.text_input("Cliente *")
        project = c2.text_input("Proyecto")
        matrix = c3.selectbox("Matriz", ["suelo", "agua", "roca", "planta", "otro"], index=0)

        description = st.text_area("Descripción / Observaciones")
        c4, c5, c6 = st.columns(3)
        received_at = c4.date_input("Fecha de recepción", value=date.today())
        due_at = c5.date_input("Fecha de entrega", value=None)
        priority = c6.selectbox("Prioridad", ["baja", "normal", "alta", "urgente"], index=1)

        c7, c8, c9 = st.columns(3)
        status = c7.selectbox("Estado", ["registrado", "en_proceso", "en_espera", "reportado", "cerrado", "cancelado"], index=0)
        location = c8.text_input("Ubicación / Almacenamiento")
        created_by = c9.text_input("Responsable de registro", value=st.session_state.user)

        submitted = st.form_submit_button("➕ Crear muestra")

        if submitted:
            if not client:
                st.error("Cliente es obligatorio.")
            else:
                sid = next_sample_id()
                run_execute(
                    """
                    INSERT INTO samples(id, client, project, matrix, description, received_at, due_at, status, priority, location, created_by, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        sid,
                        client,
                        project,
                        matrix,
                        description,
                        str(received_at),
                        str(due_at) if due_at else None,
                        status,
                        priority,
                        location,
                        created_by,
                        now_ts(),
                        now_ts(),
                    ),
                )
                audit("sample", sid, "create", st.session_state.user, {"client": client, "priority": priority})
                run_execute(
                    "INSERT INTO coc(sample_id, event, by_user, at_time, notes) VALUES(?,?,?,?,?)",
                    (sid, "Registro", st.session_state.user, now_ts(), "Muestra creada"),
                )
                st.success(f"Muestra creada: {sid}")

# ------ Muestras ------
elif page == "📦 Muestras":
    st.header("📦 Muestras")
    q = st.text_input("Buscar por ID/Cliente/Proyecto")
    status_f = st.multiselect("Estado", ["registrado", "en_proceso", "en_espera", "reportado", "cerrado", "cancelado"], default=["registrado","en_proceso","en_espera"])
    sql = "SELECT * FROM samples WHERE 1=1"
    params: List[Any] = []
    if q:
        sql += " AND (id LIKE ? OR client LIKE ? OR project LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if status_f:
        sql += " AND status IN (" + ",".join(["?"]*len(status_f)) + ")"
        params += status_f
    sql += " ORDER BY created_at DESC"

    df = pd.DataFrame(run_query(sql, tuple(params)))
    st.dataframe(df, use_container_width=True)

    st.subheader("✏️ Editar selección")
    sid = st.text_input("ID de muestra a editar")
    if sid:
        recs = run_query("SELECT * FROM samples WHERE id=?", (sid,))
        if not recs:
            st.warning("No existe esa muestra.")
        else:
            rec = recs[0]
            with st.form("edit_sample"):
                c1,c2,c3 = st.columns(3)
                client = c1.text_input("Cliente", value=rec["client"] or "")
                project = c2.text_input("Proyecto", value=rec["project"] or "")
                matrix = c3.text_input("Matriz", value=rec["matrix"] or "")
                description = st.text_area("Descripción", value=rec["description"] or "")
                c4,c5,c6 = st.columns(3)
                received_at = c4.date_input("Recepción", value=date.fromisoformat(rec["received_at"]) if rec["received_at"] else date.today())
                due_at_val = date.fromisoformat(rec["due_at"]) if rec["due_at"] else None
                due_at = c5.date_input("Entrega", value=due_at_val)
                status = c6.selectbox("Estado", ["registrado", "en_proceso", "en_espera", "reportado", "cerrado", "cancelado"], index=["registrado", "en_proceso", "en_espera", "reportado", "cerrado", "cancelado"].index(rec["status"]))
                c7,c8 = st.columns(2)
                priority = c7.selectbox("Prioridad", ["baja","normal","alta","urgente"], index=["baja","normal","alta","urgente"].index(rec["priority"]))
                location = c8.text_input("Ubicación", value=rec["location"] or "")
                save = st.form_submit_button("💾 Guardar cambios")
            if save:
                run_execute(
                    """
                    UPDATE samples SET client=?, project=?, matrix=?, description=?, received_at=?, due_at=?, status=?, priority=?, location=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        client, project, matrix, description,
                        str(received_at), str(due_at) if due_at else None,
                        status, priority, location, now_ts(), sid
                    ),
                )
                audit("sample", sid, "update", st.session_state.user, {"status": status})
                st.success("Actualizado.")

    st.subheader("➕ Añadir ensayos a una muestra")
    sid2 = st.text_input("ID de muestra")
    if sid2:
        with st.form("add_test"):
            c1,c2,c3,c4 = st.columns(4)
            test_name = c1.text_input("Ensayo *", placeholder="p.ej., FRX, AAN, ICP-OES")
            method = c2.text_input("Método", placeholder="p.ej., k0-AAN, EPA 6010D")
            unit = c3.text_input("Unidad", placeholder="mg/kg, %-m/m, etc.")
            due_at = c4.date_input("Entrega", value=None)
            submitted = st.form_submit_button("Agregar")
        if submitted and test_name:
            run_execute(
                "INSERT INTO tests(sample_id, test_name, method, unit, status, due_at) VALUES(?,?,?,?,?,?)",
                (sid2, test_name, method, unit, "pendiente", str(due_at) if due_at else None),
            )
            audit("test", sid2, "create", st.session_state.user, {"test": test_name})
            st.success("Ensayo agregado.")

# ------ Ensayos & Resultados ------
elif page == "🧫 Ensayos & Resultados":
    st.header("🧫 Ensayos & Resultados")
    filt = st.text_input("Filtrar por muestra/ensayo")
    sql = """
        SELECT t.id, t.sample_id, t.test_name, t.method, t.unit, t.status, t.assigned_to, t.due_at
        FROM tests t
        JOIN samples s ON s.id = t.sample_id
        WHERE 1=1
    """
    params: List[Any] = []
    if filt:
        sql += " AND (t.sample_id LIKE ? OR t.test_name LIKE ? OR t.method LIKE ?)"
        like = f"%{filt}%"
        params += [like, like, like]
    sql += " ORDER BY t.id DESC"
    df_t = pd.DataFrame(run_query(sql, tuple(params)))
    st.dataframe(df_t, use_container_width=True)

    st.subheader("✏️ Actualizar estado / asignación")
    tid = st.number_input("ID de ensayo", min_value=1, step=1)
    if tid:
        dft = pd.DataFrame(run_query("SELECT * FROM tests WHERE id=?", (tid,)))
        if dft.empty:
            st.info("Ingrese un ID válido")
        else:
            row = dft.iloc[0]
            with st.form("edit_test"):
                c1,c2,c3 = st.columns(3)
                status = c1.selectbox("Estado", ["pendiente","en_proceso","en_revision","reportado","cancelado"], index=["pendiente","en_proceso","en_revision","reportado","cancelado"].index(row["status"]))
                assigned_to = c2.text_input("Asignado a", value=row["assigned_to"] or st.session_state.user)
                due_at = c3.date_input("Entrega", value=date.fromisoformat(row["due_at"]) if row["due_at"] else None)
                save = st.form_submit_button("💾 Guardar")
            if save:
                run_execute(
                    "UPDATE tests SET status=?, assigned_to=?, due_at=? WHERE id=?",
                    (status, assigned_to, str(due_at) if due_at else None, tid),
                )
                audit("test", str(tid), "update", st.session_state.user, {"status": status})
                st.success("Ensayo actualizado.")

    st.subheader("🧮 Ingresar resultados")
    with st.form("add_result"):
        c1,c2,c3,c4 = st.columns(4)
        tid_r = c1.number_input("ID ensayo *", min_value=1, step=1)
        analyte = c2.text_input("Analito *", placeholder="p.ej., Fe, SiO2")
        value = c3.number_input("Valor", value=0.0)
        unit = c4.text_input("Unidad", placeholder="mg/kg, %")
        c5,c6 = st.columns(2)
        unc = c5.text_input("Incertidumbre (opcional)")
        notes = c6.text_input("Notas")
        submit_r = st.form_submit_button("➕ Añadir resultado")
    if submit_r and analyte and tid_r:
        run_execute(
            "INSERT INTO results(test_id, analyte, value, unit, uncertainty, notes, measured_at) VALUES(?,?,?,?,?,?,?)",
            (int(tid_r), analyte, float(value), unit, float(unc) if unc else None, notes, now_ts()),
        )
        audit("result", str(tid_r), "create", st.session_state.user, {"analyte": analyte})
        st.success("Resultado guardado.")

    st.subheader("📄 Resultados del ensayo (vista)")
    tid_view = st.number_input("Ver resultados de ID de ensayo", min_value=0, step=1)
    if tid_view:
        df_r = pd.DataFrame(run_query("SELECT * FROM results WHERE test_id=?", (int(tid_view),)))
        st.dataframe(df_r, use_container_width=True)

# ------ Adjuntos ------
elif page == "📎 Adjuntos / Links":
    st.header("📎 Adjuntos / Links (Google Drive, SharePoint, etc.)")
    sid = st.text_input("ID de muestra")
    with st.form("add_link"):
        c1, c2 = st.columns([2,1])
        label = c1.text_input("Etiqueta", placeholder="p.ej., Protocolo de muestreo, Carpeta Drive")
        url = c1.text_input("URL *", placeholder="https://... (PDF o carpeta)")
        notes = c2.text_input("Notas")
        add = st.form_submit_button("➕ Agregar link")
    if add and sid and url:
        run_execute(
            "INSERT INTO attachments(sample_id, label, url, added_by, added_at) VALUES(?,?,?,?,?)",
            (sid, label, url, st.session_state.user, now_ts()),
        )
        audit("attachment", sid, "create", st.session_state.user, {"url": url})
        st.success("Adjunto registrado.")

    if sid:
        df_links = pd.DataFrame(run_query("SELECT id,label,url,added_by,added_at FROM attachments WHERE sample_id=? ORDER BY id DESC", (sid,)))
        st.dataframe(df_links, use_container_width=True)

# ------ QC ------
elif page == "✅ Control de Calidad":
    st.header("✅ Control de Calidad")
    with st.form("qc_form"):
        c1,c2,c3 = st.columns(3)
        qtype = c1.selectbox("Tipo", ["calibración","mantenimiento","verificación","control interno"], index=0)
        instr = c2.text_input("Equipo/Instrumento", placeholder="Epsilon 4, Genie 2000, etc.")
        desc = c3.text_input("Descripción")
        add = st.form_submit_button("Registrar evento QC")
    if add:
        run_execute(
            "INSERT INTO qc_events(type, instrument, description, status, at_time, by_user) VALUES(?,?,?,?,?,?)",
            (qtype, instr, desc, "abierto", now_ts(), st.session_state.user),
        )
        audit("qc", "-", "create", st.session_state.user, {"type": qtype})
        st.success("Evento QC registrado.")

    df_qc = pd.DataFrame(run_query("SELECT * FROM qc_events ORDER BY id DESC"))
    st.dataframe(df_qc, use_container_width=True)

    qid = st.number_input("ID evento para cerrar", min_value=0, step=1)
    if qid:
        if st.button("Cerrar evento QC"):
            run_execute("UPDATE qc_events SET status='cerrado' WHERE id=?", (int(qid),))
            audit("qc", str(qid), "close", st.session_state.user, {})
            st.success("Evento QC cerrado.")

# ------ Reportes & Exportación ------
elif page == "📈 Reportes & Exportación":
    st.header("📈 Reportes & Exportación")

    st.subheader("Informe simple por muestra")
    sid = st.text_input("ID de muestra para reporte")
    if st.button("Generar reporte JSON") and sid:
        sample = run_query("SELECT * FROM samples WHERE id=?", (sid,))
        tests = run_query("SELECT * FROM tests WHERE sample_id=?", (sid,))
        test_ids = tuple([t["id"] for t in tests])
        results = []
        if test_ids:
            placeholders = ",".join(["?"]*len(test_ids))
            results = run_query(f"SELECT * FROM results WHERE test_id IN ({placeholders})", test_ids)
        report = {
            "generated_at": now_ts(),
            "sample": sample[0] if sample else {},
            "tests": tests,
            "results": results,
        }
        js = json.dumps(report, indent=2, ensure_ascii=False)
        st.download_button("Descargar reporte.json", js, file_name=f"reporte_{sid}.json", mime="application/json")

    st.subheader("Exportar tablas a CSV")
    tbl = st.selectbox("Tabla", ["samples","tests","results","attachments","qc_events","audit","coc"])
    if st.button("Exportar CSV"):
        df = pd.DataFrame(run_query(f"SELECT * FROM {tbl}"))
        csv = df.to_csv(index=False)
        st.download_button("Descargar CSV", csv, file_name=f"{tbl}.csv", mime="text/csv")

    st.subheader("Respaldo de base de datos")
    if st.button("Descargar lims.db"):
        with open(DB_PATH, "rb") as f:
            st.download_button("Descargar archivo lims.db", f, file_name="lims.db")

# ------ Administración ------
elif page == "⚙️ Administración":
    st.header("⚙️ Administración de usuarios")
    dfu = pd.DataFrame(run_query("SELECT id,username,role,active,created_at FROM users ORDER BY id DESC"))
    st.dataframe(dfu, use_container_width=True)

    st.subheader("➕ Nuevo usuario")
    with st.form("add_user"):
        c1,c2,c3 = st.columns(3)
        uname = c1.text_input("Usuario *")
        role = c2.selectbox("Rol", ["admin","analyst","guest"], index=1)
        active = c3.checkbox("Activo", value=True)
        add = st.form_submit_button("Crear usuario")
    if add and uname:
        try:
            run_execute("INSERT INTO users(username, role, active, created_at) VALUES(?,?,?,?)", (uname, role, 1 if active else 0, now_ts()))
            audit("user", uname, "create", st.session_state.user, {"role": role})
            st.success("Usuario creado.")
        except sqlite3.IntegrityError:
            st.error("Nombre de usuario ya existe.")

# ------ Auditoría ------
elif page == "🧾 Auditoría":
    st.header("🧾 Registro de auditoría")
    filt = st.text_input("Filtrar por entidad/acción/usuario")
    sql = "SELECT * FROM audit WHERE 1=1"
    params: List[Any] = []
    if filt:
        like = f"%{filt}%"
        sql += " AND (entity LIKE ? OR action LIKE ? OR by_user LIKE ?)"
        params += [like, like, like]
    sql += " ORDER BY id DESC LIMIT 1000"
    df_a = pd.DataFrame(run_query(sql, tuple(params)))
    st.dataframe(df_a, use_container_width=True)

    st.subheader("Cadena de custodia (por muestra)")
    sid = st.text_input("ID de muestra para ver COC")
    if sid:
        df_c = pd.DataFrame(run_query("SELECT id,event,by_user,at_time,notes FROM coc WHERE sample_id=? ORDER BY id ASC", (sid,)))
        st.dataframe(df_c, use_container_width=True)
        with st.form("add_coc"):
            c1,c2 = st.columns(2)
            event = c1.text_input("Evento *", placeholder="Recepción, Preparación, Análisis, Revisión, Entrega")
            notes = c2.text_input("Notas")
            add = st.form_submit_button("Añadir evento")
        if add and event:
            run_execute(
                "INSERT INTO coc(sample_id, event, by_user, at_time, notes) VALUES(?,?,?,?,?)",
                (sid, event, st.session_state.user, now_ts(), notes),
            )
            audit("coc", sid, "add_event", st.session_state.user, {"event": event})
            st.success("Evento agregado a la cadena de custodia.")

# =============================
# Notas finales
# =============================
st.sidebar.markdown("---")
st.sidebar.caption("Mini LIMS — v0.1 (Demo)")
