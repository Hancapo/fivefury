def ped_metadata_xml(model="actor", dictionary="face"):
    return (
        "<CPedModelInfo__InitDataList><InitDatas><Item>"
        f"<Name>{model}</Name><ExpressionDictionaryName>{dictionary}</ExpressionDictionaryName>"
        "<ExpressionName>face</ExpressionName></Item></InitDatas></CPedModelInfo__InitDataList>"
    ).encode()
