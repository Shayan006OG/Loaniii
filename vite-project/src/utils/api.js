export const verifyDocument = async (docType, number, file) => {
  try {
    const formData = new FormData();
    formData.append("doc_type", docType);
    formData.append("number", number);
    formData.append("file", file);

    const response = await fetch("http://127.0.0.1:8000/verify", {
      method: "POST",
      body: formData
    });

    if (!response.ok) throw new Error("Network response not ok");
    const data = await response.json();
    return data;

  } catch (error) {
    console.error("Verification error:", error);
    return { status: "Rejected", feedback: "Server error" };
  }
};
