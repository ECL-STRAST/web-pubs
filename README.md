# web-pubs

A catalog of the theses and scientific publications of the research group.
Each entry holds its metadata, an English summary, the compiled PDF, links to
the attached code and docs repositories, and an optional presentation. The
site is published from `main` to GitHub Pages.

LaTeX sources and anything not cleared for publication live in the private
repository `ECL-STRAST/web-pubs-private`. Presence in *this* repository is
what makes an entry public; there is no flag to get wrong.

## Layout

    content/theses/<year>-<slug>/   entry.yaml, summary.md, thesis.pdf, slides.pdf
    content/publications/<year>-<slug>/ same shape, kind instead of degree;
                                      paper.pdf only if shareable
    taxonomy/topics.yaml            the controlled topic vocabulary
    tools/pubs/                      the tooling
    site/                           build output, gitignored

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[dev]"
    export OVERLEAF_GIT_TOKEN=...
    git clone git@github.com:ECL-STRAST/web-pubs-private.git ../web-pubs-private

`latexmk` and a TeX distribution are needed to add or sync entries, but not
to build the site.

### LaTeX requirements

A minimal TeX install is not enough. The group's theses need:
`acronym appendix booktabs enumitem eso-pic eurosym fancyvrb float framed
mathrsfs mathtools minted multirow placeins siunitx subfig titlesec xcolor`.
On Debian/Ubuntu:

    sudo apt install texlive-latex-extra texlive-latex-recommended \
            texlive-science texlive-fonts-extra python3-pygments

`texlive-full` also works if you'd rather not think about it.
`python3-pygments` is required because `minted` shells out to it.

`pubs` compiles with `-shell-escape` for `minted`, which lets the document
run shell commands during compilation. Only compile sources you trust.

## Adding a thesis

    pubs add thesis --overleaf <project-id> --name nieves-serrano-biomechanics-db

Title, author, year, degree, programme, supervisors, summary and keywords
are read from the LaTeX source. The year becomes the slug's prefix, so
the entry lands in `content/theses/<year>-<name>/`.

Extraction reads the group's template: `\tfgtitle`, `\authorname`,
`\supervisor` and `\fecha` in `main.tex`, the cover phrase
(`TRABAJO FIN DE GRADO`, `... DE MÁSTER`, `TESIS DOCTORAL`), the
programme named just above it on the same page (`GRADO EN ...`,
`MÁSTER EN ...`), and the chapter holding `\chapter*{Abstract}` with its
`\textbf{Keywords:}` line. A thesis on another template simply has no
programme; that is not an error and there is no flag for it. A field it
cannot find aborts the command by name; `--title`, `--author`, `--year`
and `--degree` supply one by hand for a thesis built on another template.

Then replace the `CHANGE-ME` topic with tags from `taxonomy/topics.yaml`,
adding any missing tag to that file first. Topics are curated and drive
the site's filter; the extracted `keywords` are the thesis's own words,
are displayed but never filtered, and are not checked against the
vocabulary. Finally:

    pubs validate

`validate` checks schema, topics, referenced files, and repo URL syntax.
It never checks that a URL is reachable: CI holds no secrets and reaches
nothing, and group repos may be private.

Entries may be added before the work is defended: a draft PDF, no attached
repositories and no slides are all valid.

Don't forget to push to this repo after adding a new thesis or making any
change to an existing one if you want the GitHub pages to update.

### Fields you fill in by hand

| Field | Notes |
|---|---|
| `topics` | from `taxonomy/topics.yaml`; a filter facet |
| `kind` | papers only; from the list above; the publications' filter facet |
| `score` | 0 to 10 |
| `honours` | `true` for Matrícula de Honor; needs a `score` |
| `photo` | the author's portrait, a file in the entry folder, e.g. `photo.jpg` |
| `image` | a figure from the thesis, a file in the entry folder, e.g. `cover.png` |
| `video` | a YouTube or Vimeo URL, e.g. `https://vimeo.com/76979871` |
| `author_github` | the author's GitHub profile, e.g. `https://github.com/bgomezm` |
| `author_linkedin` | the author's LinkedIn profile, e.g. `https://www.linkedin.com/in/bgomezm` |
| `repos`, `slides` | as before |

`supervisors` is no longer hand-entered: it is read from the
`\supervisor` macro and rewritten on every sync.

Only three video URL shapes are accepted —
`https://www.youtube.com/watch?v=<id>`, `https://youtu.be/<id>` and
`https://vimeo.com/<digits>`. Anything else is rejected by `validate`.
The stored URL is parsed into a provider id and never reaches the page's
`iframe`, because `entry.yaml` arrives through pull requests.

A student's portrait is personal data, and so is a recognisable student
in an `image` or a `video`. Get their written consent before committing
one, and note that removing it later means rewriting this repository's
history.

### Keeping an entry current

    pubs sync <slug>

Re-pulls from Overleaf, recompiles, and re-reads the metadata.
`summary.md` is **derived from the abstract and is rewritten on every
sync** — do not hand-edit it; edit the thesis. Your own fields (`topics`,
`score`, `honours`, `photo`, `image`, `video`, `author_github`,
`author_linkedin`, `repos`, `slides`) are preserved; `supervisors` is not — it is re-read from the source. If the
thesis's year changes, `sync` updates the field and warns, but does not
rename the folder: the slug is an identifier and shared URLs must keep
working.

## Adding a paper

    pubs add paper --doi 10.1109/TVCG.2026.1234567 --name autor-mocap

Title, authors in order, year, venue, keywords and the abstract (when
the registry carries one) come from CrossRef, falling back to DataCite.
The slug still needs `--name`: it is a URL others will cite. A DOI the
registries do not know aborts; so does one without a year.

A paper has a `kind` — `conference`, `journal`, `poster`, `workshop`,
`book_chapter`, `book` or `preprint` — as much its category as the
degree is a thesis's. Pass `--kind journal` or replace the `CHANGE-ME`
the command scaffolds; `validate` reports it until you do.

Then replace the `CHANGE-ME` topic as with a thesis. `pubs sync <slug>`
re-reads the registries and refreshes title, authors, year, venue,
keywords and published; your own fields and `summary.md` are never touched.

Drop `paper.pdf` in the folder only if the rights allow it — publisher
PDFs usually may not be hosted, accepted manuscripts often may. A
paywalled paper is listed by its citation alone: the page links the
DOI. Presence in this repo remains the clearance for the file; the
citation itself is public knowledge and is not withheld.

### Changing one field

To change a field you own — a score, a photo, an image, a video — edit
`content/theses/<slug>/entry.yaml` and run:

    pubs validate && pubs build

Do **not** use `pubs sync` for this. Sync re-pulls from Overleaf and
recompiles the LaTeX; it is for picking up changes to the thesis itself,
not for applying your own edits.

## Other commands

    pubs sync <slug>     re-pull from Overleaf and recompile
    pubs build           render site/ locally
