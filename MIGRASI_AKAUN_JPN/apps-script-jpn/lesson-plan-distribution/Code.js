/**
 * Niat → Save to Google Drive + Upload to Google Classroom
 *
 * ONE-TIME SETUP:
 *   In the script editor, click "Services" (the + on the left) →
 *   "Google Classroom API" → Add.
 *
 * STEP 1 — find your Classroom:
 *   Leave COURSE_ID = "" below and Run "niatToClassroom" once.
 *   Click "Review permissions" → Allow. Open the Execution log to see the list
 *   of your Classrooms and their IDs.
 * STEP 2 — post it:
 *   Copy the ID of your designated RPH Classroom into COURSE_ID below, then Run again.
 *   The lesson plan is saved to your Google Drive AND posted to that Classroom.
 */
var COURSE_ID = "";  // Set only after choosing a Classroom owned or taught by the JPN account.

function niatToClassroom() {
  var DATA = {
  "planTitle": "RPH — 3 Delima (2026-07-09)",
  "planRows": [
    [
      "MINGGU",
      "23"
    ],
    [
      "TARIKH",
      "2026-07-09"
    ],
    [
      "HARI",
      "Thursday"
    ],
    [
      "MASA",
      "8.40 a.m."
    ],
    [
      "TINGKATAN / KELAS",
      "3 Delima"
    ],
    [
      "MINIMUM JAM SETAHUN",
      "144"
    ],
    [
      "MATA PELAJARAN",
      "Bahasa Inggeris"
    ],
    [
      "TEMA / BIDANG",
      "Consumerism and Financial Awareness"
    ],
    [
      "TAJUK",
      "Unit 5: A Place to Call Home"
    ],
    [
      "STANDARD KANDUNGAN",
      "4.2 Communicate with appropriate language, form and style"
    ],
    [
      "STANDARD PEMBELAJARAN",
      "4.2.1 Punctuate written work with moderate accuracy.\n4.2.3 Produce a plan or draft of two paragraphs or more and modify this appropriately independently."
    ],
    [
      "OBJEKTIF PEMBELAJARAN",
      "Pada akhir PdPc, murid boleh :\n1. correct punctuation errors in short descriptive sentences with moderate accuracy.\n2. create a plan for a descriptive paragraph about an ideal home.\n3. draft a short descriptive paragraph based on their plan, demonstrating basic modification skills."
    ],
    [
      "AKTIVITI PEMBELAJARAN",
      "1. Set Induction: Teacher displays images of various types of homes (e.g., modern house, traditional kampong house, apartment, treehouse). Students are asked: \"What kind of home do you dream of having?\" or \"What makes a home special?\" A brief discussion activates prior knowledge and interest.\n2. Step 1: Punctuation Practice (21st CL: Collaborative Learning). Teacher distributes a short paragraph or a few sentences related to homes/descriptions containing common punctuation errors (e.g., missing capital letters, commas, full stops, apostrophes). In pairs, students identify and correct the errors. Teacher reviews corrections with the class, explaining rules. (CCE: Language – focus on accurate writing conventions).\n3. Step 2: Planning an Ideal Home Description (HOTS: Applying). Teacher introduces the writing task: \"Describe your ideal home in a paragraph or two.\" Students brainstorm ideas as a class (What features would it have? What would it look like? How would it feel?). Students then use a simple graphic organiser (e.g., a mind map or bullet points) to plan their description, considering adjectives, sensory details, and key features.\n4. Step 3: Drafting and Modifying (21st CL: Collaborative Learning, HOTS: Applying). Students draft their descriptive paragraph(s) based on their plan. Teacher circulates, providing guidance and reminding students to apply correct punctuation and sentence structure. Once a draft is complete, students exchange drafts with a partner for a quick peer check (focusing on clarity, basic grammar, and punctuation). They then modify their own draft based on feedback.\n5. Closure: Teacher asks a few students to share one interesting sentence or phrase from their description. Teacher recaps the importance of planning before writing and checking for punctuation and grammar. Homework: Students are assigned to refine their descriptive paragraph(s) at home."
    ],
    [
      "REFLEKSI",
      ""
    ]
  ]
};

  // STEP 1: list the Classrooms you teach, so you can copy the right ID.
  if (!COURSE_ID) {
    var list = Classroom.Courses.list({ teacherId: "me", courseStates: ["ACTIVE"] });
    var courses = (list && list.courses) || [];
    if (!courses.length) { Logger.log("No active Classrooms found where you are a teacher."); return; }
    Logger.log("=== Your Google Classrooms — copy the ID of your designated RPH class ===");
    courses.forEach(function (c) { Logger.log(c.name + "   ->   COURSE_ID = \"" + c.id + "\""); });
    Logger.log("Paste the correct ID into COURSE_ID at the top, then Run again.");
    return;
  }

  // STEP 2a: create the lesson plan as a Google Doc in your Drive.
  var doc = DocumentApp.create(DATA.planTitle);
  var body = doc.getBody();
  body.appendParagraph("RANCANGAN PELAJARAN HARIAN").setHeading(DocumentApp.ParagraphHeading.HEADING1);
  if (DATA.planRows.length) {
    var table = body.appendTable(DATA.planRows);
    for (var i = 0; i < DATA.planRows.length; i++) { table.getCell(i, 0).editAsText().setBold(true); }
  }
  doc.saveAndClose();

  // STEP 2b: post the Doc to the designated Classroom as a Material.
  Classroom.Courses.CourseWorkMaterials.create({
    title: DATA.planTitle,
    description: "Daily Lesson Plan (RPH) — uploaded by Niat.",
    materials: [{ driveFile: { driveFile: { id: doc.getId() }, shareMode: "VIEW" } }],
    state: "PUBLISHED"
  }, COURSE_ID);

  Logger.log("Saved to Drive: " + doc.getUrl());
  Logger.log("Posted to Classroom course ID: " + COURSE_ID);
}
