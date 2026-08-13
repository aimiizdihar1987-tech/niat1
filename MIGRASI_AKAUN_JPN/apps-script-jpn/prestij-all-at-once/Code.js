/**
 * Niat Hub — ONE-TIME deploy. After this, Niat posts lesson plans and
 * worksheets to Google Classroom with one click (no more Apps Script visits).
 *
 * SETUP (10 minutes, once):
 *  1. Go to https://script.google.com -> New project. Delete the sample code,
 *     paste ALL of this file in.
 *  2. Left sidebar: Services (+) -> "Google Classroom API" -> Add.
 *  3. (Optional) change SECRET_KEY below.
 *  4. Deploy -> New deployment -> type: Web app.
 *       Execute as: Me    |    Who has access: Anyone
 *     Click Deploy, Allow all permissions, then COPY the Web app URL (/exec).
 *  5. In the Niat folder, open reminder_config.txt and add:
 *       APPSCRIPT_HUB_URL=<the /exec url>
 *       APPSCRIPT_HUB_KEY=<the same SECRET_KEY>
 *  Done. The buttons in Niat now send directly.
 *
 * It handles:
 *   - lesson plans  -> Google Doc + PDF -> posted to your "Lesson Plan" Classroom
 *   - worksheets    -> Google Form quiz -> assignment in the pupils' Classroom
 *                      (with due date) + emailed to pilot students
 *   - reminder mail -> (fallback for school WiFi that blocks normal email)
 *   - submissions   -> who has / hasn't turned in an assignment (Agent 6)
 *   - overdue       -> every assignment past its due date (Agent 6 cron)
 *
 * WHY submissions/overdue live here: reading Classroom submissions from the
 * Niat server needs a Google Cloud OAuth app the MOE admin must approve first.
 * The hub already runs AS THE TEACHER, so it can read her own classes today —
 * no admin approval needed. Agent 6 uses this whenever Path B isn't set up.
 *
 * If Apps Script ever says a permission is missing for the two Classroom reads,
 * open Project Settings -> tick "Show appsscript.json", then add to that file:
 *   "oauthScopes": [
 *     "https://www.googleapis.com/auth/script.external_request",
 *     "https://www.googleapis.com/auth/documents",
 *     "https://www.googleapis.com/auth/presentations",
 *     "https://www.googleapis.com/auth/forms",
 *     "https://www.googleapis.com/auth/drive",
 *     "https://www.googleapis.com/auth/classroom.courses",
 *     "https://www.googleapis.com/auth/classroom.coursework.students",
 *     "https://www.googleapis.com/auth/classroom.rosters.readonly",
 *     "https://www.googleapis.com/auth/classroom.profile.emails",
 *     "https://mail.google.com/"
 *   ]
 * then Deploy -> Manage deployments -> edit -> New version, and re-authorise.
 */

var SECRET_KEY = "oC4LYSGPIqop3JzJr6YizeVQ4G4iVg7f1-OqjUKp3oc";

/**
 * Run this ONCE from the editor (Run > authorizeOnce) whenever Google asks
 * for new permissions - it triggers the permission prompt for every service
 * the hub uses, then cleans up after itself.
 */
function authorizeOnce() {
  var createdIds = [];
  var doc = DocumentApp.create("PRESTIJ JPN auth check");
  createdIds.push(doc.getId());
  doc.saveAndClose();

  var form = FormApp.create("PRESTIJ JPN auth check");
  createdIds.push(form.getId());

  var deck = SlidesApp.create("PRESTIJ JPN auth check");
  createdIds.push(deck.getId());
  deck.saveAndClose();

  createdIds.forEach(function (id) {
    DriveApp.getFileById(id).setTrashed(true);
  });

  var courses = Classroom.Courses.list({
    teacherId: "me",
    courseStates: ["ACTIVE"],
    pageSize: 100
  });
  var audit = migrationAudit();
  audit.ok = true;
  audit.activeClassrooms = (courses.courses || []).length;
  Logger.log(JSON.stringify(audit));
  return audit;
}

/** Migration verification. Runs only through the API as the JPN deployer. */
function migrationAudit() {
  var triggers = ScriptApp.getProjectTriggers().map(function (trigger) {
    return {
      functionName: trigger.getHandlerFunction(),
      eventType: String(trigger.getEventType()),
      source: String(trigger.getTriggerSource()),
      uniqueId: trigger.getUniqueId()
    };
  });
  var result = {
    effectiveUser: Session.getEffectiveUser().getEmail(),
    timeZone: Session.getScriptTimeZone(),
    triggers: triggers
  };
  Logger.log(JSON.stringify(result));
  return result;
}

function doPost(e) {
  var out = { ok: false };
  try {
    var expected = (typeof SECRET_KEY !== "undefined") ? SECRET_KEY : "";
    var d = JSON.parse(e.postData.contents);
    if (expected && d.key !== expected) {
      return _json({ ok: false, error: "forbidden (wrong key)" });
    }
    var action = d.action || (d.to ? "mail" : "");
    if (action === "mail") out = doMail(d);
    else if (action === "lessonplan") out = doLessonPlan(d);
    else if (action === "worksheet") out = doWorksheet(d);
    else if (action === "materials") out = doMaterials(d);
    else if (action === "results") out = doResults(d);
    else if (action === "submissions") out = doSubmissions(d);
    else if (action === "overdue") out = doOverdue(d);
    else out = { ok: false, error: "unknown action: " + action };
  } catch (err) {
    out = { ok: false, error: String(err) };
  }
  return _json(out);
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ---- reminder email over HTTPS (school WiFi blocks SMTP) -------------------
function doMail(d) {
  MailApp.sendEmail({ to: d.to, subject: d.subject || "[Niat]", body: d.body || "" });
  return { ok: true, sent: d.to };
}

// ---- lesson plan -> Doc + PDF -> Lesson Plan Classroom ---------------------
function doLessonPlan(d) {
  var doc = DocumentApp.create(d.title || "RPH");
  var body = doc.getBody();
  if (d.school) {
    body.appendParagraph(String(d.school).toUpperCase())
        .setHeading(DocumentApp.ParagraphHeading.HEADING2).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  }
  body.appendParagraph("RANCANGAN PENGAJARAN HARIAN")
      .setHeading(DocumentApp.ParagraphHeading.HEADING1).setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  if (d.rows && d.rows.length) {
    var table = body.appendTable(d.rows);
    for (var i = 0; i < d.rows.length; i++) table.getCell(i, 0).editAsText().setBold(true);
  }
  doc.saveAndClose();
  var docUrl = doc.getUrl();
  var pdfBlob = DriveApp.getFileById(doc.getId()).getAs("application/pdf")
      .setName((d.title || "RPH") + ".pdf");
  var pdfUrl = DriveApp.createFile(pdfBlob).getUrl();

  var postUrl = "";
  if (d.courseId) {
    var material = Classroom.Courses.CourseWorkMaterials.create({
      title: d.title || "RPH",
      description: "Auto-posted by Niat.",
      materials: [{ link: { url: docUrl, title: d.title || "RPH" } }],
      state: "PUBLISHED"
    }, d.courseId);
    postUrl = material.alternateLink || "";
  }
  return { ok: true, doc_url: docUrl, pdf_url: pdfUrl, classroom_url: postUrl };
}

// ---- teaching slides -> Google Slides -> chosen Classroom ------------------
function doMaterials(d) {
  var deck = SlidesApp.create(d.title || "Slides");
  var first = deck.getSlides();
  (d.slides || []).forEach(function (s, idx) {
    var slide = (idx === 0) ? first[0] : deck.appendSlide(SlidesApp.PredefinedLayout.BLANK);
    var h = slide.insertTextBox(s.heading || ("Slide " + (idx + 1)), 36, 28, 648, 70);
    h.getText().getTextStyle().setBold(true).setFontSize(26);
    if (s.points && s.points.length) {
      var lines = s.points.map(function (x) { return "•  " + x; }).join("\n\n");
      var b = slide.insertTextBox(lines, 44, 110, 632, 300);
      b.getText().getTextStyle().setFontSize(15);
    }
  });
  deck.saveAndClose();
  var url = deck.getUrl();
  var postUrl = "";
  if (d.courseId) {
    var material = Classroom.Courses.CourseWorkMaterials.create({
      title: d.title || "Slides",
      description: "Teaching slides - auto-posted by Niat.",
      materials: [{ link: { url: url, title: d.title || "Slides" } }],
      state: "PUBLISHED"
    }, d.courseId);
    postUrl = material.alternateLink || "";
  }
  return { ok: true, slides_url: url, classroom_url: postUrl };
}

// ---- worksheet -> Form quiz -> class Classroom + student emails ------------
function doWorksheet(d) {
  var ws = d.ws || {};
  var form = FormApp.create(ws.title || "Niat Quiz");
  form.setIsQuiz(true);
  form.setDescription(d.description || "");
  try { form.setCollectEmail(true); } catch (e) { /* newer Forms may block this; ignore */ }
  (ws.questions || []).forEach(function (item) {
    var mc = form.addMultipleChoiceItem();
    var choices = item.opts.map(function (opt, i) {
      return mc.createChoice(opt, i === item.answerIndex);
    });
    mc.setTitle(item.q).setChoices(choices).setPoints(item.points || 1).setRequired(true);
    if (item.feedback) {
      var fb = FormApp.createFeedback().setText(item.feedback).build();
      mc.setFeedbackForCorrect(fb); mc.setFeedbackForIncorrect(fb);
    }
  });
  var formUrl = form.getPublishedUrl();

  var cwUrl = "", cwStatus = "no courseId given";
  if (d.courseId) {
    var work = {
      title: ws.title || "Niat Quiz",
      description: d.description || "",
      materials: [{ link: { url: formUrl, title: ws.title || "Quiz" } }],
      workType: "ASSIGNMENT",
      state: "PUBLISHED",
      maxPoints: ws.points || 100
    };
    if (d.dueIso) {
      var dd = new Date(d.dueIso);
      work.dueDate = { year: dd.getUTCFullYear(), month: dd.getUTCMonth() + 1, day: dd.getUTCDate() };
      work.dueTime = { hours: dd.getUTCHours(), minutes: dd.getUTCMinutes() };
    }
    var cw = Classroom.Courses.CourseWork.create(work, d.courseId);
    cwUrl = cw.alternateLink || "";
    cwStatus = "posted";
  }

  var emailed = 0;
  (d.studentEmails || []).forEach(function (st) {
    try {
      MailApp.sendEmail({
        to: st.email || st,
        subject: "[Niat] " + (ws.title || "English Quiz"),
        htmlBody: "Hi " + (st.name || "there") + "!<br><br>" +
                  String(d.description || "").replace(/\n/g, "<br>") + "<br><br>" +
                  "Open the quiz: <a href=\"" + formUrl + "\">" + formUrl + "</a><br><br>" +
                  "Good luck!<br>— Niat, your class assistant"
      });
      emailed++;
    } catch (err) { /* keep going for the rest */ }
  });

  return { ok: true, form_url: formUrl, form_id: form.getId(), classroom_url: cwUrl,
           classroom_status: cwStatus, students_emailed: emailed };
}

// ==========================================================================
// AGENT 6 — reading Google Classroom submissions
// ==========================================================================

/** Find an ACTIVE course by id, or by exact/partial name ("3 Delima"). */
function _findCourse(courseId, courseName) {
  if (courseId) {
    try { return Classroom.Courses.get(courseId); } catch (e) { /* fall through to name */ }
  }
  var want = String(courseName || "").trim().toLowerCase();
  if (!want) return null;
  var page = null, exact = null, partial = null;
  do {
    var resp = Classroom.Courses.list({
      teacherId: "me", courseStates: ["ACTIVE"], pageSize: 100, pageToken: page
    });
    (resp.courses || []).forEach(function (c) {
      var nm = String(c.name || "").toLowerCase();
      if (nm === want) exact = exact || c;
      else if (nm.indexOf(want) >= 0 || want.indexOf(nm) >= 0) partial = partial || c;
    });
    page = resp.nextPageToken;
  } while (page && !exact);
  return exact || partial;
}

/** Every courseWork item in a course (handles paging). */
function _allCourseWork(courseId) {
  var items = [], page = null;
  do {
    var resp = Classroom.Courses.CourseWork.list(courseId, { pageSize: 100, pageToken: page });
    items = items.concat(resp.courseWork || []);
    page = resp.nextPageToken;
  } while (page);
  return items;
}

/** dueDate/dueTime (UTC) -> "YYYY-MM-DDTHH:MM", or "" if the work has no due date. */
function _dueIso(work) {
  var dd = work.dueDate, dt = work.dueTime || {};
  if (!dd) return "";
  var p = function (n) { return ("0" + n).slice(-2); };
  return dd.year + "-" + p(dd.month) + "-" + p(dd.day) + "T" +
         p(dt.hours || 23) + ":" + p(dt.minutes || 59);
}

/**
 * Who has / hasn't turned in an assignment.
 * In:  {courseId | courseName, title}   (no title = the newest assignment)
 * Out: {ok, course, coursework, due_iso, classroom_url,
 *       students:[{email, name, userId, state, submitted, late}]}
 * Mirrors niat_google.list_submission_states so Agent 6 can use either source.
 */
function doSubmissions(d) {
  var course = _findCourse(d.courseId, d.courseName);
  if (!course) {
    return { ok: false, error: 'No active Classroom matching "' + (d.courseName || d.courseId) + '"' };
  }
  var items = _allCourseWork(course.id);
  if (!items.length) return { ok: false, error: "No assignments in " + course.name };

  var want = String(d.title || "").trim().toLowerCase(), work = null;
  if (want) {
    for (var i = 0; i < items.length && !work; i++) {
      var nm = String(items[i].title || "").toLowerCase();
      if (nm === want || nm.indexOf(want) >= 0) work = items[i];
    }
    if (!work) return { ok: false, error: 'No assignment matching "' + d.title + '" in ' + course.name };
  } else {
    items.sort(function (a, b) { return String(b.creationTime).localeCompare(String(a.creationTime)); });
    work = items[0];
  }

  // Roster: userId -> {email, name}. Emails need classroom.profile.emails.
  var roster = {}, page = null;
  do {
    var r = Classroom.Courses.Students.list(course.id, { pageSize: 100, pageToken: page });
    (r.students || []).forEach(function (s) {
      var p = s.profile || {};
      roster[s.userId] = {
        email: (p.emailAddress || ""),
        name: ((p.name || {}).fullName || "")
      };
    });
    page = r.nextPageToken;
  } while (page);

  var students = [];
  page = null;
  do {
    var sub = Classroom.Courses.CourseWork.StudentSubmissions.list(
      course.id, work.id, { pageSize: 100, pageToken: page });
    (sub.studentSubmissions || []).forEach(function (s) {
      var state = s.state || "NEW";
      var who = roster[s.userId] || {};
      students.push({
        userId: s.userId, email: who.email || "", name: who.name || "",
        state: state, submitted: (state === "TURNED_IN" || state === "RETURNED"),
        late: !!s.late
      });
    });
    page = sub.nextPageToken;
  } while (page);

  return { ok: true, course: course.name, coursework: work.title || "",
           due_iso: _dueIso(work), classroom_url: work.alternateLink || "",
           students: students };
}

/**
 * Every assignment whose due date has PASSED but is no older than withinDays —
 * the work list for the Agent 6 cron.
 * In:  {withinDays}   Out: {ok, assignments:[{class_name, coursework_title, due_iso}]}
 */
function doOverdue(d) {
  var within = parseInt(d.withinDays, 10) || 14;
  var now = new Date();
  var floor = new Date(now.getTime() - within * 24 * 60 * 60 * 1000);
  var out = [], page = null;
  do {
    var resp = Classroom.Courses.list({
      teacherId: "me", courseStates: ["ACTIVE"], pageSize: 100, pageToken: page
    });
    (resp.courses || []).forEach(function (course) {
      _allCourseWork(course.id).forEach(function (w) {
        var dd = w.dueDate, dt = w.dueTime || {};
        if (!dd) return;
        var due = new Date(Date.UTC(dd.year, dd.month - 1, dd.day,
                                    dt.hours || 23, dt.minutes || 59));
        if (due >= floor && due < now) {
          out.push({ class_name: course.name || "", coursework_title: w.title || "",
                     due_iso: _dueIso(w) });
        }
      });
    });
    page = resp.nextPageToken;
  } while (page);
  out.sort(function (a, b) { return b.due_iso.localeCompare(a.due_iso); });
  return { ok: true, assignments: out };
}

// ---- read a quiz's responses -> average, weakest questions, per-student ----
// Called by Niat's "Fetch results" button. The hub runs as the teacher, who
// owns the form, so it can read every response. Identify the form by id
// (preferred) or by its exact title (most recent one wins).
function doResults(d) {
  var form = null;
  if (d.formId) {
    try { form = FormApp.openById(d.formId); } catch (e) { form = null; }
  }
  if (!form && d.title) {
    var files = DriveApp.getFilesByName(d.title), newest = null;
    while (files.hasNext()) {
      var f = files.next();
      if (f.getMimeType() === "application/vnd.google-apps.form" &&
          (!newest || f.getLastUpdated() > newest.getLastUpdated())) newest = f;
    }
    if (newest) { try { form = FormApp.openById(newest.getId()); } catch (e) { form = null; } }
  }
  if (!form) return { ok: false, error: "Quiz form not found. Make sure it was created by Niat." };

  // Max possible points = sum of each graded item's points.
  var maxTotal = 0, items = form.getItems(FormApp.ItemType.MULTIPLE_CHOICE);
  items.forEach(function (it) { maxTotal += (it.asMultipleChoiceItem().getPoints() || 1); });
  if (!maxTotal) maxTotal = items.length || 1;

  var responses = form.getResponses();
  var n = responses.length;
  if (!n) return { ok: true, respondents: 0, average_percent: null,
                   title: form.getTitle(), message: "No responses yet." };

  var sumPct = 0, correctCount = {}, perStudent = [];
  responses.forEach(function (resp) {
    var g = resp.getGradableItemResponses(), earned = 0;
    g.forEach(function (item, i) {
      var s = item.getScore() || 0;
      earned += s;
      correctCount[i] = (correctCount[i] || 0) + (s > 0 ? 1 : 0);
    });
    var pct = Math.round(earned / maxTotal * 100);
    sumPct += pct;
    perStudent.push({ email: resp.getRespondentEmail() || "(anonymous)",
                      score: earned, max: maxTotal, percent: pct });
  });

  var avg = Math.round(sumPct / n);
  var perQuestion = Object.keys(correctCount).map(function (k) {
    return { q: parseInt(k, 10) + 1, correct_percent: Math.round(correctCount[k] / n * 100) };
  });
  var weakest = perQuestion.slice().sort(function (a, b) {
    return a.correct_percent - b.correct_percent;
  }).slice(0, 3);

  return { ok: true, title: form.getTitle(), respondents: n,
           average_percent: avg, max_points: maxTotal,
           per_question: perQuestion, weakest: weakest, per_student: perStudent };
}
