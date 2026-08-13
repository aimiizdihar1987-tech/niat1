import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const packageRoot = new URL("../", import.meta.url);
const manifestUrl = new URL("../roster-manifest.json", import.meta.url);
const localEnvUrl = new URL("../.env.local", import.meta.url);
const allowedClasses = new Set(["3 Delima", "3 Zamrud", "3 Berlian"]);
const allowedLevels = new Set(["advanced", "intermediate", "lower_achiever"]);
const emailPattern = /^m-[a-z0-9][a-z0-9._-]*@moe-dl\.edu\.my$/i;

async function loadLocalEnv() {
  try {
    const text = await readFile(localEnvUrl, "utf8");
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const separator = line.indexOf("=");
      if (separator < 1) continue;
      const key = line.slice(0, separator).trim();
      const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, "");
      if (!(key in process.env)) process.env[key] = value;
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function loadManifest() {
  const manifest = JSON.parse(await readFile(manifestUrl, "utf8"));
  if (!Array.isArray(manifest.records) || manifest.records.length !== 9) {
    throw new Error("roster-manifest.json mesti mempunyai tepat 9 rekod.");
  }
  return manifest;
}

function requireEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Pemboleh ubah ${name} belum diisi.`);
  return value;
}

async function buildRows() {
  await loadLocalEnv();
  const manifest = await loadManifest();
  const rows = manifest.records.map((record) => {
    if (!allowedClasses.has(record.className)) throw new Error(`Kelas tidak sah dalam manifest: ${record.className}`);
    if (!allowedLevels.has(record.achievementLevel)) throw new Error(`Tahap tidak sah dalam manifest: ${record.achievementLevel}`);
    const email = requireEnv(record.emailEnv).toLowerCase();
    if (!emailPattern.test(email)) throw new Error(`${record.emailEnv} bukan alamat MOE-DL yang sah.`);
    return {
      student_email: email,
      class_name: record.className,
      achievement_level: record.achievementLevel,
      is_active: true,
      source: "classroom_invite_confirmed_by_user",
      updated_at: new Date().toISOString(),
    };
  });

  if (new Set(rows.map((row) => row.student_email)).size !== rows.length) {
    throw new Error("Alamat e-mel mesti unik bagi semua 9 rekod.");
  }
  return rows;
}

function summary(rows) {
  return Object.fromEntries(
    [...allowedClasses].map((className) => [className, rows.filter((row) => row.class_name === className).length]),
  );
}

async function syncSupabase(rows) {
  const baseUrl = requireEnv("SUPABASE_URL").replace(/\/$/, "");
  const serviceRoleKey = requireEnv("SUPABASE_SERVICE_ROLE_KEY");
  const response = await fetch(`${baseUrl}/rest/v1/classroom_members?on_conflict=student_email`, {
    method: "POST",
    headers: {
      apikey: serviceRoleKey,
      Authorization: `Bearer ${serviceRoleKey}`,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates,return=minimal",
    },
    body: JSON.stringify(rows),
  });
  if (!response.ok) throw new Error(`Supabase menolak permintaan (HTTP ${response.status}).`);
  console.log(JSON.stringify({ target: "supabase", synced: rows.length, classes: summary(rows) }, null, 2));
}

const firestoreString = (stringValue) => ({ stringValue });

async function syncFirestore(rows) {
  const projectId = requireEnv("GCP_PROJECT_ID");
  const token = requireEnv("GOOGLE_OAUTH_ACCESS_TOKEN");
  const databaseId = process.env.FIRESTORE_DATABASE_ID?.trim() || "(default)";
  const databasePath = `projects/${projectId}/databases/${databaseId}`;
  const writes = rows.map((row) => {
    const documentId = createHash("sha256").update(row.student_email).digest("hex").slice(0, 32);
    return {
      update: {
        name: `${databasePath}/documents/classroom_members/${documentId}`,
        fields: {
          student_email: firestoreString(row.student_email),
          class_name: firestoreString(row.class_name),
          achievement_level: firestoreString(row.achievement_level),
          source: firestoreString(row.source),
          is_active: { booleanValue: true },
          updated_at: { timestampValue: row.updated_at },
        },
      },
      updateMask: {
        fieldPaths: [
          "student_email",
          "class_name",
          "achievement_level",
          "source",
          "is_active",
          "updated_at",
        ],
      },
    };
  });

  const endpoint = `https://firestore.googleapis.com/v1/${databasePath}/documents:commit`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ writes }),
  });
  if (!response.ok) throw new Error(`Firestore menolak permintaan (HTTP ${response.status}).`);
  console.log(JSON.stringify({ target: "firestore", synced: rows.length, classes: summary(rows) }, null, 2));
}

async function main() {
  const command = process.argv[2] ?? "validate";
  if (!new Set(["validate", "supabase", "firestore"]).has(command)) {
    throw new Error("Arahan mesti salah satu: validate, supabase, firestore.");
  }
  const rows = await buildRows();
  if (command === "validate") {
    console.log(JSON.stringify({ valid: true, records: rows.length, classes: summary(rows), packageRoot: packageRoot.pathname }, null, 2));
    return;
  }
  if (command === "supabase") await syncSupabase(rows);
  if (command === "firestore") await syncFirestore(rows);
}

main().catch((error) => {
  console.error(`Gagal: ${error.message}`);
  process.exitCode = 1;
});
