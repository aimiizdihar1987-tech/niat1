/**
 * Niat → Distribute
 *
 * HOW TO USE:
 *  1. Go to  https://script.google.com  and click "New project".
 *  2. Delete the sample code, then paste ALL of this in.
 *  3. Enable the Classroom service: in the left sidebar click "Services +",
 *     choose "Google Classroom API", click Add.
 *  4. Click Save (disk icon), then Run the function "niatDistribute".
 *  5. Click "Review permissions" and Allow (first time only).
 *  6. Check the Execution log. It will:
 *       • save the LESSON PLAN as a Google Doc in your Drive + email it to you,
 *       • create the WORKSHEET as a Google Form quiz, and
 *       • post that quiz to your Google Classroom class as an assignment with a due date.
 */
function niatDistribute() {
  var DATA = {
  "planTitle": "Lesson Plan — 3 Delima (2026-07-09)",
  "planRows": [
    [
      "MINGGU",
      "24"
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
      "8.40-10.10 a.m."
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
      "People and Culture"
    ],
    [
      "TAJUK",
      "Unit 2: Food, Food, Food!"
    ],
    [
      "STANDARD KANDUNGAN",
      "3.2 Explore and expand ideas for personal development by reading independently and widely"
    ],
    [
      "STANDARD PEMBELAJARAN",
      "3.2.1 Read, enjoy and give a personal response to fiction or non-fiction and other suitable print and digital texts of interest."
    ],
    [
      "OBJEKTIF PEMBELAJARAN",
      "Pada akhir PdPc, murid boleh :\n1. identify at least three key pieces of information about different food items from the given text.\n2. express their personal opinions and preferences regarding the food items discussed in the text."
    ],
    [
      "AKTIVITI PEMBELAJARAN",
      "1. Set Induction: Teacher displays pictures of various traditional Malaysian foods and asks students to name their favourite and briefly explain why. (5 minutes)\n2. Step 1: Teacher distributes a non-fiction text (e.g., an article from the textbook or supplementary material) describing different traditional foods from various cultures. Students read the text individually and highlight or note down key information about each food item (e.g., origin, main ingredients, unique preparation). (25 minutes)\n3. Step 2: Students work in pairs for a 'Think-Pair-Share' activity. First, they discuss the key information they identified from the text. Then, they share their personal responses to questions such as: 'Which food described in the text would you most like to try and why?' and 'What does this text tell us about the importance of food in different cultures?' (35 minutes)\n4. Step 3: Selected pairs share their discussions and personal responses with the whole class. The teacher facilitates a brief class discussion, emphasising the value of appreciating diverse food cultures and traditions. (20 minutes)\n5. Closure: Teacher summarises the different foods discussed and reiterates the importance of respecting diverse food cultures. Students are asked to reflect on one new food item or cultural aspect they learned about today. (5 minutes)"
    ],
    [
      "REFLEKSI",
      ""
    ]
  ],
  "planEmail": "jpn-perlis-cm16@moe-dl.edu.my",
  "slides": [
    {
      "heading": "Unit 2: Food, Food, Food!",
      "body": [
        "People and Culture",
        "3 Delima",
        "2026-07-09"
      ]
    },
    {
      "heading": "Learning Objectives",
      "body": [
        "identify at least three key pieces of information about different food items from the given text.",
        "express their personal opinions and preferences regarding the food items discussed in the text."
      ]
    },
    {
      "heading": "Lesson Activities",
      "body": [
        "Set Induction: Teacher displays pictures of various traditional Malaysian foods and asks students to name their favourite and briefly explain why. (5 minutes)",
        "Step 1: Teacher distributes a non-fiction text (e.g., an article from the textbook or supplementary material) describing different traditional foods from various cultures. Students read the text individually and highlight or note down key information about each food item (e.g., origin, main ingredients, unique preparation). (25 minutes)",
        "Step 2: Students work in pairs for a 'Think-Pair-Share' activity. First, they discuss the key information they identified from the text. Then, they share their personal responses to questions such as: 'Which food described in the text would you most like to try and why?' and 'What does this text tell us about the importance of food in different cultures?' (35 minutes)",
        "Step 3: Selected pairs share their discussions and personal responses with the whole class. The teacher facilitates a brief class discussion, emphasising the value of appreciating diverse food cultures and traditions. (20 minutes)",
        "Closure: Teacher summarises the different foods discussed and reiterates the importance of respecting diverse food cultures. Students are asked to reflect on one new food item or cultural aspect they learned about today. (5 minutes)"
      ]
    }
  ],
  "students": [
    {
      "name": "Student A",
      "email": "profantastic63@gmail.com"
    },
    {
      "name": "Student B",
      "email": "capmomentphotography@gmail.com"
    },
    {
      "name": "Cikgu Aimi",
      "email": "jpn-perlis-cm16@moe-dl.edu.my"
    }
  ],
  "ws": {
    "title": "English Quiz: Food, Food, Food! (Reading)",
    "desc": "Class: 3 Delima  •  Date: 2026-07-09  •  Generated by Niat",
    "questions": [
      {
        "q": "What is a popular Chinese dish made from noodles, meat, and vegetables?",
        "opts": [
          "Rice",
          "Noodle Soup",
          "Lo Mein",
          "Wonton Noodles"
        ],
        "answerIndex": 2,
        "points": 1,
        "feedback": "The correct answer is Lo Mein because it is a Chinese dish made from noodles, meat, and vegetables."
      },
      {
        "q": "What is a traditional Japanese tea ceremony?",
        "opts": [
          "A sake tasting",
          "A sushi making",
          "A tea serving",
          "A flower arrangement"
        ],
        "answerIndex": 2,
        "points": 1,
        "feedback": "The correct answer is A tea serving because it is a traditional Japanese tea ceremony."
      },
      {
        "q": "What is a common ingredient in Indian curries?",
        "opts": [
          "Rice",
          "Noodles",
          "Cumin",
          "Coriander"
        ],
        "answerIndex": 3,
        "points": 1,
        "feedback": "The correct answer is Coriander because it is a common ingredient in Indian curries."
      },
      {
        "q": "What is a popular French dessert?",
        "opts": [
          "Tarte",
          "Quiche",
          "Crème Brûlée",
          "Macaron"
        ],
        "answerIndex": 2,
        "points": 1,
        "feedback": "The correct answer is Crème Brûlée because it is a popular French dessert."
      },
      {
        "q": "If you eat too much spicy food, what might happen to your stomach?",
        "opts": [
          "It will be full",
          "It will be empty",
          "It may hurt",
          "It will get bigger"
        ],
        "answerIndex": 2,
        "points": 1,
        "feedback": "The correct answer is It may hurt because if you eat too much spicy food, it can irritate your stomach."
      },
      {
        "q": "Why do people often have breakfast to start their day?",
        "opts": [
          "Because they are hungry",
          "Because they want to eat something sweet",
          "Because it helps them focus",
          "Because it gives them energy"
        ],
        "answerIndex": 2,
        "points": 1,
        "feedback": "The correct answer is Because it gives them energy because breakfast helps provide energy for the day ahead."
      },
      {
        "q": "How does food bring people together in different cultures?",
        "opts": [
          "It makes them separate",
          "It keeps them busy",
          "It helps them communicate",
          "It brings people together"
        ],
        "answerIndex": 2,
        "points": 2,
        "feedback": "The correct answer is It brings people together because food often plays a central role in social gatherings and celebrations across cultures."
      },
      {
        "q": "What are some ways that traditional cuisine can reflect a country's history and culture?",
        "opts": [
          "Only through ingredients",
          "Only through cooking methods",
          "Through both ingredients and cooking methods",
          "Neither"
        ],
        "answerIndex": 2,
        "points": 2,
        "feedback": "The correct answer is Through both ingredients and cooking methods because traditional cuisine often incorporates local ingredients and cooking techniques that are unique to a country's history and culture."
      },
      {
        "q": "What is a common food item that people in different countries have at breakfast?",
        "opts": [
          "Eggs",
          "Bread",
          "Juice",
          "Cereal"
        ],
        "answerIndex": 0,
        "points": 1,
        "feedback": "The correct answer is Eggs because eggs are a common food item that people in many countries have at breakfast."
      },
      {
        "q": "What is the name of the popular Indian dish made from lentils?",
        "opts": [
          "Tandoori Chicken",
          "Biryani Rice",
          "Dal Makhani",
          "Samosa"
        ],
        "answerIndex": 2,
        "points": 1,
        "feedback": "The correct answer is Dal Makhani because it is a popular Indian dish made from lentils."
      }
    ],
    "points": 12
  },
  "classroom": {
    "className": "3 Delima",
    "dueIso": "2026-07-16T21:00:00+08:00",
    "dueLocal": "2026-07-16 21:00",
    "title": "English Quiz: Food, Food, Food! (Reading)",
    "description": "Hi everyone! This short quiz checks what you learned about food and culture. There are 10 multiple-choice questions and it marks itself. Read each question carefully, choose the best answer, and submit before the due date. Good luck!\n\nDue date: 2026-07-16 21:00 — please submit before then."
  }
};

  // ---- 1) Lesson plan -> Google Doc in Drive + email the teacher ----
  var doc = DocumentApp.create(DATA.planTitle);
  var body = doc.getBody();
  body.appendParagraph(DATA.planTitle).setHeading(DocumentApp.ParagraphHeading.HEADING1);
  if (DATA.planRows.length) {
    var table = body.appendTable(DATA.planRows);
    for (var i = 0; i < DATA.planRows.length; i++) {
      table.getCell(i, 0).editAsText().setBold(true);
    }
  }
  doc.saveAndClose();
  var docUrl = doc.getUrl();
  // Convert the lesson plan to PDF and save it in Drive.
  var pdfBlob = DriveApp.getFileById(doc.getId()).getAs("application/pdf").setName(DATA.planTitle + ".pdf");
  var pdfFile = DriveApp.createFile(pdfBlob);
  var pdfUrl = pdfFile.getUrl();
  if (DATA.planEmail) {
    MailApp.sendEmail({
      to: DATA.planEmail,
      subject: "[Niat] Lesson Plan (PDF) — " + DATA.planTitle,
      htmlBody: "Your lesson plan is attached as a PDF and saved to your Google Drive.<br><br>" +
                "PDF: <a href=\"" + pdfUrl + "\">" + pdfUrl + "</a><br>" +
                "Editable Doc: <a href=\"" + docUrl + "\">" + docUrl + "</a>",
      attachments: [pdfBlob]
    });
  }

  // ---- 2) Worksheet -> Google Form quiz ----
  var form = FormApp.create(DATA.ws.title);
  form.setIsQuiz(true);
  form.setDescription(DATA.classroom.description);
  form.setCollectEmail(true);
  DATA.ws.questions.forEach(function (item) {
    var mc = form.addMultipleChoiceItem();
    var choices = item.opts.map(function (opt, i) {
      return mc.createChoice(opt, i === item.answerIndex);
    });
    mc.setTitle(item.q).setChoices(choices).setPoints(item.points).setRequired(true);
    if (item.feedback) {
      var fb = FormApp.createFeedback().setText(item.feedback).build();
      mc.setFeedbackForCorrect(fb);
      mc.setFeedbackForIncorrect(fb);
    }
  });
  var formUrl = form.getPublishedUrl();

  // QR code (students scan to open the quiz; the teacher can project or print it).
  var qrUrl = "https://quickchart.io/qr?size=320&margin=2&text=" + encodeURIComponent(formUrl);
  if (DATA.planEmail) {
    MailApp.sendEmail({
      to: DATA.planEmail,
      subject: "[Niat] Quiz QR — " + DATA.ws.title,
      htmlBody: "Show or print this QR code for pupils to open the quiz:<br><br>" +
                "<img src=\"" + qrUrl + "\" width=\"260\" height=\"260\"><br><br>" +
                "Or share this link: <a href=\"" + formUrl + "\">" + formUrl + "</a>"
    });
  }

  // ---- 2c) Email the quiz link directly to the pilot students ----
  var studentsSent = 0;
  (DATA.students || []).forEach(function (st) {
    try {
      MailApp.sendEmail({
        to: st.email,
        subject: "[Niat] " + DATA.ws.title,
        htmlBody: "Hi " + (st.name || "there") + "!<br><br>" +
                  DATA.classroom.description.replace(/\n/g, "<br>") + "<br><br>" +
                  "Open the quiz here: <a href=\"" + formUrl + "\">" + formUrl + "</a><br><br>" +
                  "Good luck!<br>— Niat, your class assistant"
      });
      studentsSent++;
    } catch (e) { Logger.log("Student email FAILED for " + st.email + ": " + e); }
  });
  Logger.log("Quiz emailed to " + studentsSent + " of " + (DATA.students || []).length + " pilot student(s).");

  // ---- 3) Post the worksheet to Google Classroom (assignment + due date) ----
  var classroomStatus = "not posted";
  try {
    var courses = (Classroom.Courses.list({ courseStates: ["ACTIVE"] }).courses) || [];
    var want = (DATA.classroom.className || "").toLowerCase();
    var target = null;
    for (var j = 0; j < courses.length; j++) {
      var nm = (courses[j].name || "").toLowerCase();
      if (want && (nm === want || nm.indexOf(want) > -1)) { target = courses[j]; break; }
    }
    if (!target) {
      classroomStatus = 'NO active Classroom class matching "' + DATA.classroom.className +
        '". Share this quiz link manually: ' + formUrl;
    } else {
      var work = {
        title: DATA.classroom.title,
        description: DATA.classroom.description,
        materials: [{ link: { url: formUrl, title: DATA.ws.title } }],
        workType: "ASSIGNMENT",
        state: "PUBLISHED",
        maxPoints: DATA.ws.points || 100
      };
      if (DATA.classroom.dueIso) {
        var dd = new Date(DATA.classroom.dueIso);  // due time is in Malaysia time (UTC+8)
        work.dueDate = { year: dd.getUTCFullYear(), month: dd.getUTCMonth() + 1, day: dd.getUTCDate() };
        work.dueTime = { hours: dd.getUTCHours(), minutes: dd.getUTCMinutes() };
      }
      var cw = Classroom.Courses.CourseWork.create(work, target.id);
      classroomStatus = 'posted to "' + target.name + '"' +
        (DATA.classroom.dueLocal ? " (due " + DATA.classroom.dueLocal + ")" : "") +
        " -> " + cw.alternateLink;
    }
  } catch (e) {
    classroomStatus = "Classroom step failed: " + e + " | Quiz link to share manually: " + formUrl;
  }

  // ---- 4) Lesson plan -> Google Slides teaching deck ----
  var slidesUrl = "";
  try {
    var deck = SlidesApp.create("Slides — " + DATA.planTitle);
    var existing = deck.getSlides();
    DATA.slides.forEach(function (s, idx) {
      var slide = (idx === 0) ? existing[0] : deck.appendSlide(SlidesApp.PredefinedLayout.BLANK);
      var h = slide.insertTextBox(s.heading, 36, 28, 648, 70);
      h.getText().getTextStyle().setBold(true).setFontSize(26);
      if (s.body && s.body.length) {
        var lines = s.body.map(function (x) { return "•  " + x; }).join("\n\n");
        var b = slide.insertTextBox(lines, 44, 110, 632, 300);
        b.getText().getTextStyle().setFontSize(15);
      }
    });
    deck.saveAndClose();
    slidesUrl = deck.getUrl();
    if (DATA.planEmail) {
      MailApp.sendEmail({
        to: DATA.planEmail,
        subject: "[Niat] Teaching Slides — " + DATA.planTitle,
        htmlBody: "Your teaching slides are ready in Google Slides:<br><br>" +
                  "<a href=\"" + slidesUrl + "\">" + slidesUrl + "</a>"
      });
    }
  } catch (e) {
    slidesUrl = "Slides step skipped: " + e;
  }

  Logger.log("Lesson plan doc (Drive + emailed): " + docUrl);
  Logger.log("Lesson plan PDF: " + pdfUrl);
  Logger.log("Teaching slides: " + slidesUrl);
  Logger.log("Worksheet form: " + formUrl);
  Logger.log("Quiz QR: " + qrUrl);
  Logger.log("Classroom: " + classroomStatus);
}
