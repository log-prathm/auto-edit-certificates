# Introduction 

This repo contains code for automatic certificate labeling - such as adding names and some other information at partcular position in an image/pdf en masse.

---



## For pdf template =>

`
python make_certificates.py \
  --template certificate.pdf \
  --names names.csv \
  --names-column name \
  --outdir output \
  --y 310 --box-h 90 \
  --font "C:/Windows/Fonts/arial.ttf" \
  --font-size 42 \
  --color "#1a1a1a"
`

## For images template =>


### Good command for central text ->

`
python main.py --template certificate.jpeg --names names.txt --outdir output --y 410 --box-h 120 --font "C:/Windows/Fonts/BRUSHSCI.TTF" --font-size 48
`

To add color to the text, do --color "color-code"

### Examples of names.txt

`Prathmesh Lagdive

Vaibhav Aglave

Ganesh Ghumare`

### Examples of names.csv

`name

"Prathmesh Lagdive"

"Vaibhav Aglave"
`


# If you can see this repo, Use it for free.

- Prathmesh Lagdive