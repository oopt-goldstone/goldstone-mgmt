use anyhow::Result;
use lazy_static::lazy_static;
use regex::Regex;

lazy_static! {
    static ref XPATH_ELEMENT_RE: Regex =
        Regex::new(r"^(?:(?P<prefix>[-\w]+):)?(?P<name>[-\w\*]+)").unwrap();
}

type Elems<'a> = Vec<(Option<&'a str>, &'a str, Vec<(&'a str, &'a str)>)>;

pub fn xpath_split(xpath: &str) -> Result<Elems> {
    if xpath.is_empty() {
        return Err(anyhow::anyhow!("empty xpath"));
    }

    let mut i = 0;
    let mut output = vec![];
    loop {
        if let Some(0) = &xpath[i..].find('/') {
            i += 1;
        };
        let caps = XPATH_ELEMENT_RE.captures(&xpath[i..]).unwrap();
        i += caps.get(0).unwrap().end();

        let mut cond = vec![];

        loop {
            if let Some(0) = &xpath[i..].find('[') {
                i += 1; // skip opening '['
            } else {
                break;
            }
            if let Some(j) = &xpath[i..].find('=') {
                let k = i + j;
                let key = &xpath[i..k];
                let quote = &xpath[k + 1..k + 2]; // record opening quote character
                i = k + 2; // skip '=' and opening quote
                if let Some(l) = &xpath[i..].find(quote) {
                    let k = i + l;
                    let value = &xpath[i..k];
                    cond.push((key, value));
                    i = k + 2; // skip closing quote and ']'
                } else {
                    return Err(anyhow::anyhow!("no closing quote"));
                }
            } else {
                return Err(anyhow::anyhow!("couldn't find '='"));
            }
        }

        output.push((
            caps.name("prefix").map(|m| m.as_str()),
            caps.name("name").unwrap().as_str(),
            cond,
        ));
        if xpath.len() <= i {
            break;
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use crate::xpath::*;

    #[test]
    fn test_xpath_split() {
        let elems = xpath_split("/a:b/c[k='v']/p2:d").unwrap();
        assert_eq!(elems.len(), 3);
        assert_eq!(elems[0].0, Some("a"));
        assert_eq!(elems[0].1, "b");
        assert_eq!(elems[0].2.len(), 0);
        assert_eq!(elems[1].0, None);
        assert_eq!(elems[1].1, "c");
        assert_eq!(elems[1].2.len(), 1);
        assert_eq!(elems[1].2[0], ("k", "v"));
        assert_eq!(elems[2].0, Some("p2"));
        assert_eq!(elems[2].1, "d");
        assert_eq!(elems[2].2.len(), 0);
    }
}
