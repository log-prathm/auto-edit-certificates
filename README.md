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
  --x 220 --y 310 --box-w 700 --box-h 90 \
  --font "C:/Windows/Fonts/arial.ttf" \
  --font-size 42 \
  --color "#1a1a1a"
`

## For images template =>

`
python make_certificates.py \
  --template certificate.png \
  --names names.txt \
  --outdir output \
  --x 220 --y 310 --box-w 700 --box-h 90 \
  --font "C:/Windows/Fonts/arial.ttf" \
  --font-size 42
`

## Good command for central text ->

`
python main.py --template certificate.jpeg --names names.txt --outdir output --x 280 --y 370 --box-w 700 --box-h 210 --font "C:/Windows/Fonts/BRUSHSCI.ttf" --font-size 38
`

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