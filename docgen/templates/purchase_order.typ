// Official Purchase Order Typst Template
// PT Bali Towerindo Sentra Tbk - Enterprise Autonomous Procurement System

#set page(
  paper: "a4",
  margin: (x: 1.6cm, top: 1.6cm, bottom: 1.6cm),
  header: align(right)[
    #text(size: 8pt, fill: rgb("#64748b"))[
      PT Bali Towerindo Sentra Tbk | Official Enterprise Procurement Document
    ]
  ],
  footer: [
    #line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))
    #v(3pt)
    #grid(
      columns: (1fr, 1fr),
      align: (left, right),
      [
        #text(size: 7.5pt, fill: rgb("#94a3b8"))[
          Dokumen Purchase Order Resmi diterbitkan secara otomatis oleh BaliTowerOps AI Enterprise System.
        ]
      ],
      [
        #text(size: 7.5pt, fill: rgb("#94a3b8"))[
          Halaman 1 dari 1 — Arsip Digital Bali Tower
        ]
      ]
    )
  ]
)

#set text(
  font: ("Segoe UI", "Roboto", "Liberation Sans", "Arial"),
  size: 9pt,
  fill: rgb("#1e293b")
)

#let po_status = "{{STATUS}}"
#let status_color = if po_status == "DELIVERED" { rgb("#16a34a") } else { rgb("#d97706") }
#let status_bg = if po_status == "DELIVERED" { rgb("#f0fdf4") } else { rgb("#fffbeb") }
#let status_border = if po_status == "DELIVERED" { rgb("#bbf7d0") } else { rgb("#fde68a") }

// Header Kop Surat Perusahaan
#grid(
  columns: (1.2fr, 1fr),
  align: (left, right),
  [
    #text(size: 15pt, weight: "bold", fill: rgb("#0f172a"))[PT BALI TOWERINDO SENTRA TBK]\
    #v(-2pt)
    #text(size: 9pt, weight: "semibold", fill: rgb("#0284c7"))[TELECOMMUNICATION INFRASTRUCTURE & FIBER OPTIC SOLUTIONS]\
    #v(2pt)
    #text(size: 8pt, fill: rgb("#64748b"))[
      Wisma Kodel Lantai 6, Jl. H.R. Rasuna Said Kav. B-4\
      Karet Kuningan, Setiabudi, Jakarta Selatan 12920, Indonesia\
      Telepon: (021) 522-8888 | Email: procurement\@balitower.co.id | www.balitower.co.id
    ]
  ],
  [
    #text(size: 16pt, weight: "bold", fill: rgb("#0284c7"))[PURCHASE ORDER]\
    #text(size: 9pt, weight: "bold", fill: rgb("#475569"))[SURAT PESANAN RESMI PENGADAAN]\
    #v(4pt)
    #rect(
      stroke: status_border,
      radius: 4pt,
      fill: status_bg,
      inset: (x: 8pt, y: 6pt),
      align(left)[
        #grid(
          columns: (80pt, 1fr),
          row-gutter: 3pt,
          [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[No. PO Resmi:]],
          [#text(size: 8.5pt, weight: "bold", fill: rgb("#0369a1"))[{{PO_NUMBER}}]],
          [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Ref ID PO:]],
          [#text(size: 8.5pt, weight: "bold", fill: rgb("#0f172a"))[{{PO_ID}}]],
          [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Tanggal Order:]],
          [#text(size: 8pt, weight: "medium")[{{ORDER_DATE}}]],
          [#text(size: 8pt, weight: "bold", fill: rgb("#475569"))[Status Pesanan:]],
          [#text(size: 8pt, weight: "bold", fill: status_color)[{{STATUS}}]]
        )
      ]
    )
  ]
)

#v(6pt)
#line(length: 100%, stroke: 1.5pt + rgb("#0284c7"))
#v(6pt)

// Bagian 2: Informasi Vendor & Gudang Tujuan Pengiriman (2 Box)
#grid(
  columns: (1fr, 1fr),
  gutter: 12pt,
  [
    #rect(
      width: 100%,
      stroke: rgb("#cbd5e1"),
      radius: 4pt,
      fill: rgb("#f8fafc"),
      inset: 8pt,
      [
        #text(size: 8pt, weight: "bold", fill: rgb("#0284c7"))[VENDOR / REKANAN PENYEDIA:]\
        #v(3pt)
        #text(size: 10.5pt, weight: "bold", fill: rgb("#0f172a"))[{{SUPPLIER_NAME}}]\
        #v(2pt)
        #text(size: 8pt, fill: rgb("#475569"))[
          *Kode Supplier:* {{SUPPLIER_ID}}\
          *Kategori:* {{SUPPLIER_CATEGORY}}\
          *Telepon:* {{SUPPLIER_PHONE}}\
          *Email:* {{SUPPLIER_EMAIL}}\
          *Syarat Pembayaran:* #text(weight: "bold", fill: rgb("#0369a1"))[{{PAYMENT_TERMS}}]
        ]
      ]
    )
  ],
  [
    #rect(
      width: 100%,
      stroke: rgb("#cbd5e1"),
      radius: 4pt,
      fill: rgb("#f8fafc"),
      inset: 8pt,
      [
        #text(size: 8pt, weight: "bold", fill: rgb("#0284c7"))[TUJUAN PENGIRIMAN LOGISTIK FISIK:]\
        #v(3pt)
        #text(size: 10.5pt, weight: "bold", fill: rgb("#0f172a"))[{{WAREHOUSE_NAME}}]\
        #v(2pt)
        #text(size: 8pt, fill: rgb("#475569"))[
          *Kode Gudang:* {{WAREHOUSE_ID}} | *Wilayah:* {{WAREHOUSE_REGION}}\
          *Alamat Gudang:* {{WAREHOUSE_ADDRESS}}\
          *Supervisor Gudang (PIC):* #text(weight: "bold")[{{WAREHOUSE_SUPERVISOR}}]\
          *Target Kedatangan:* {{EXPECTED_DELIVERY}}\
          *Realisasi Tiba:* #text(weight: "bold", fill: status_color)[{{ACTUAL_DELIVERY}}]
        ]
      ]
    )
  ]
)

#v(8pt)
#text(size: 10pt, weight: "bold", fill: rgb("#0f172a"))[RINCIAN MATERIAL & PESANAN PENGADAAN]
#v(3pt)

// Tabel Item Material
#table(
  columns: (22pt, 75pt, 1fr, 80pt, 50pt, 70pt, 80pt),
  align: (center, left, left, left, center, right, right),
  stroke: (x, y) => if y == 0 { (bottom: 1.5pt + rgb("#0284c7")) } else { (bottom: 0.5pt + rgb("#e2e8f0")) },
  fill: (x, y) => if y == 0 { rgb("#f1f5f9") } else if calc.even(y) { rgb("#fafafa") } else { white },
  inset: (x: 5pt, y: 7pt),
  
  // Headers
  [*No*], [*Kode SKU*], [*Deskripsi Material & Spesifikasi*], [*Kategori*], [*Volume*], [*Harga Satuan*], [*Total Harga*],
  
  // Rows injected by Python
  {{ITEMS_TABLE_ROWS}}
)

#v(6pt)

// Ringkasan Finansial & Kalkulasi Pajak PPN
#grid(
  columns: (1.2fr, 1fr),
  gutter: 12pt,
  [
    #rect(
      width: 100%,
      stroke: rgb("#e2e8f0"),
      radius: 4pt,
      fill: rgb("#f8fafc"),
      inset: 8pt,
      [
        #text(size: 8pt, weight: "bold", fill: rgb("#475569"))[TERBILANG (INDONESIAN WORDS):]\
        #v(3pt)
        #text(size: 8.5pt, weight: "medium", style: "italic", fill: rgb("#0369a1"))[{{TERBILANG_WORDS}}]\
        #v(6pt)
        #text(size: 7.5pt, fill: rgb("#64748b"))[
          *Syarat & Ketentuan Pengadaan PT Bali Towerindo Sentra Tbk:*\
          1. Seluruh barang fisik wajib sesuai spesifikasi teknis telekomunikasi dalam kondisi 100% baru.\
          2. Surat Jalan resmi wajib diverifikasi dan ditandatangani oleh Supervisor Gudang tujuan.\
          3. Penagihan invoice melampirkan PO asli, Berita Acara Serah Terima (BAST), dan Faktur Pajak.
        ]
      ]
    )
  ],
  [
    #rect(
      width: 100%,
      stroke: rgb("#cbd5e1"),
      radius: 4pt,
      fill: rgb("#ffffff"),
      inset: 8pt,
      [
        #grid(
          columns: (1fr, 1fr),
          row-gutter: 5pt,
          align: (left, right),
          [#text(size: 8.5pt, fill: rgb("#64748b"))[Subtotal Pengadaan:]],
          [#text(size: 8.5pt, weight: "semibold")[{{SUBTOTAL_FMT}}]],
          [#text(size: 8.5pt, fill: rgb("#64748b"))[PPN 11% (Pajak):]],
          [#text(size: 8.5pt, weight: "semibold")[{{PPN_FMT}}]],
          [#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))],
          [#line(length: 100%, stroke: 0.5pt + rgb("#cbd5e1"))],
          [#text(size: 9.5pt, weight: "bold", fill: rgb("#0f172a"))[TOTAL PO (IDR):]],
          [#text(size: 11pt, weight: "bold", fill: rgb("#0284c7"))[{{GRAND_TOTAL_FMT}}]]
        )
      ]
    )
  ]
)

#v(10pt)

// Blok Tanda Tangan & Otorisasi Resmi Korporat
#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 10pt,
  align: center,
  [
    #rect(
      width: 100%,
      stroke: rgb("#e2e8f0"),
      radius: 4pt,
      fill: rgb("#f8fafc"),
      inset: 8pt,
      [
        #text(size: 7.5pt, weight: "bold", fill: rgb("#64748b"))[DITERBITKAN OLEH:]\
        #v(35pt)
        #text(size: 8.5pt, weight: "bold", fill: rgb("#0f172a"))[Dimas Prasetyo]\
        #line(length: 80%, stroke: 0.5pt + rgb("#94a3b8"))
        #text(size: 7pt, fill: rgb("#64748b"))[Procurement Officer (Logistik)]
      ]
    )
  ],
  [
    #rect(
      width: 100%,
      stroke: rgb("#e2e8f0"),
      radius: 4pt,
      fill: rgb("#f8fafc"),
      inset: 8pt,
      [
        #text(size: 7.5pt, weight: "bold", fill: rgb("#64748b"))[DISETUJUI OLEH (APPROVAL):]\
        #v(35pt)
        #text(size: 8.5pt, weight: "bold", fill: rgb("#0f172a"))[Bambang Soediro, S.T.]\
        #line(length: 80%, stroke: 0.5pt + rgb("#94a3b8"))
        #text(size: 7pt, fill: rgb("#64748b"))[VP Supply Chain & Infrastructure]
      ]
    )
  ],
  [
    #rect(
      width: 100%,
      stroke: rgb("#e2e8f0"),
      radius: 4pt,
      fill: rgb("#f8fafc"),
      inset: 8pt,
      [
        #text(size: 7.5pt, weight: "bold", fill: rgb("#64748b"))[PENERIMA FISIK GUDANG:]\
        #v(35pt)
        #text(size: 8.5pt, weight: "bold", fill: rgb("#0f172a"))[{{WAREHOUSE_SUPERVISOR}}]\
        #line(length: 80%, stroke: 0.5pt + rgb("#94a3b8"))
        #text(size: 7pt, fill: rgb("#64748b"))[Supervisor Gudang Regional]
      ]
    )
  ]
)

#v(8pt)
#rect(
  width: 100%,
  stroke: 1pt + rgb("#bbf7d0"),
  radius: 3pt,
  fill: rgb("#f0fdf4"),
  inset: (x: 8pt, y: 5pt),
  align(center)[
    #text(size: 7.5pt, weight: "bold", fill: rgb("#15803D"))[
      VERIFIKASI DIGITAL: DOKUMEN SAH ENTERPRISE PT BALI TOWERINDO SENTRA TBK — TERINTEGRASI DUCKDB & TYPST
    ]
  ]
)
